"""Opt-in, provider-sourced follower statistics for published creator kits."""

import uuid
from datetime import timedelta
from urllib.parse import quote

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.gating import PlanLimitExceeded, check_feature
from apps.channels.models import ChannelConnection
from apps.channels.transport import ProviderError, request
from apps.platform_ops.security import assert_enabled, pause_guard
from apps.tenants.dispatch import enqueue_once

from .models import CreatorKit


@shared_task(ignore_result=True)
def dispatch_creator_metrics():
    now = timezone.now()
    CreatorKit.all_objects.filter(
        live_stats_token__isnull=False, live_stats_started_at__lt=now - timedelta(minutes=10)
    ).update(live_stats_token=None, live_stats_next_at=now, live_stats_error="worker_interrupted")
    for wid, pk in CreatorKit.all_objects.filter(
        live_stats_next_at__lte=now, live_stats_token__isnull=True
    ).values_list("workspace_id", "pk")[:50]:
        enqueue_once(refresh_creator_metrics, wid, pk)


@shared_task(ignore_result=True, soft_time_limit=210, time_limit=240)
@pause_guard("integration:instagram")
def refresh_creator_metrics(workspace_id, kit_id):
    with transaction.atomic():
        kit = (
            CreatorKit.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(
                pk=kit_id, live_stats_next_at__lte=timezone.now(), live_stats_token__isnull=True
            )
            .first()
        )
        if not kit or not kit.live_connection_ids:
            return
        token = uuid.uuid4()
        kit.live_stats_token, kit.live_stats_started_at = token, timezone.now()
        kit.save(update_fields=["live_stats_token", "live_stats_started_at"])
        ids = kit.live_connection_ids
    error, results = "", []
    try:
        check_feature(workspace_id, "integrations_unlocked")
        connections = list(
            ChannelConnection.objects.for_workspace(workspace_id).filter(
                pk__in=ids,
                provider="instagram",
                status="active",
                is_test=False,
                expires_at__gt=timezone.now(),
            )
        )
        if len(connections) != len(ids):
            raise ProviderError("connection_unavailable")
        for connection in connections:
            body = request(
                "GET",
                f"https://graph.instagram.com/{settings.META_API_VERSION}/{quote(connection.external_account_id, safe='')}",
                headers={"Authorization": f"Bearer {connection.access_token}"},
                params={"fields": "followers_count"},
            )
            count = body.get("followers_count")
            if type(count) is not int or count < 0:
                raise ProviderError("statistics_unavailable")
            results.append((connection.pk, count))
    except PlanLimitExceeded:
        error = "plan_limit"
    except Exception:
        error = "statistics_unavailable"
    with transaction.atomic():
        kit = (
            CreatorKit.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=kit_id, live_stats_token=token)
            .first()
        )
        if not kit:
            return
        now = timezone.now()
        if not error:
            try:
                check_feature(workspace_id, "integrations_unlocked")
                assert_enabled(workspace_id, "integration:instagram")
                with transaction.atomic():
                    for connection_id, count in results:
                        connection = (
                            ChannelConnection.objects.for_workspace(workspace_id)
                            .select_for_update()
                            .get(
                                pk=connection_id, status="active", is_test=False, expires_at__gt=now
                            )
                        )
                        connection.profile = {
                            **connection.profile,
                            "followers_count": count,
                            "creator_stats_checked_at": now.isoformat(),
                        }
                        connection.save(update_fields=["profile"])
            except Exception:
                error = "connection_or_plan_changed"
        kit.live_stats_token, kit.live_stats_error, kit.live_stats_checked_at = None, error, now
        kit.live_stats_next_at = now + timedelta(minutes=15 if error else 60)
        kit.save()
