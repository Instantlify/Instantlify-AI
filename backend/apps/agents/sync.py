"""Opt-in, durable refresh schedules for connected knowledge sources."""

import uuid
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gating import PlanLimitExceeded, check_feature
from apps.crm.models import IntegrationConfig
from apps.platform_ops.security import pause_guard
from apps.tenants.dispatch import enqueue_once
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import KnowledgeSourceSync
from .sources import source_text, store_snapshot

PROVIDERS = ["google_sheets", "airtable", "notion", "shopify"]
INTERVALS = [60, 360, 1440]


class ScheduleSerializer(serializers.ModelSerializer):
    interval_minutes = serializers.ChoiceField(choices=INTERVALS, default=60)

    class Meta:
        model = KnowledgeSourceSync
        fields = [
            "enabled",
            "interval_minutes",
            "status",
            "next_run_at",
            "last_checked_at",
            "last_success_at",
            "error_code",
        ]
        read_only_fields = fields[2:]
        extra_kwargs = {"enabled": {"required": True}}


class KnowledgeSyncView(APIView):
    def integration(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        return get_object_or_404(
            IntegrationConfig.objects.for_workspace(workspace_id), pk=pk, provider__in=PROVIDERS
        )

    def get(self, request, workspace_id, pk):
        config = self.integration(request, workspace_id, pk)
        row = (
            KnowledgeSourceSync.objects.for_workspace(workspace_id)
            .filter(integration=config)
            .first()
        )
        return Response(ScheduleSerializer(row or KnowledgeSourceSync()).data)

    def put(self, request, workspace_id, pk):
        config = self.integration(request, workspace_id, pk)
        data = ScheduleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        enabled = data.validated_data["enabled"]
        if enabled:
            check_feature(workspace_id, "integrations_unlocked")
            check_feature(workspace_id, "ai_agent_enabled")
            if not config.enabled or config.status != "active":
                raise serializers.ValidationError(
                    "Reconnect this integration before enabling automatic sync."
                )
        with transaction.atomic():
            row, _ = (
                KnowledgeSourceSync.objects.for_workspace(workspace_id)
                .select_for_update()
                .get_or_create(integration=config, defaults={"workspace_id": workspace_id})
            )
            row.enabled = enabled
            row.interval_minutes = data.validated_data["interval_minutes"]
            row.next_run_at = timezone.now() if enabled else None
            # Invalidate an in-flight fetch: it must never apply after being disabled.
            row.status, row.lease_token, row.started_at, row.error_code = "idle", None, None, ""
            row.save()
            audit(config.workspace, request.user, "knowledge.sync_configured", config.pk)
        return Response(ScheduleSerializer(row).data)


def dispatch_source_syncs():
    now = timezone.now()
    KnowledgeSourceSync.all_objects.filter(
        status="running", started_at__lt=now - timedelta(minutes=10)
    ).update(status="error", lease_token=None, next_run_at=now, error_code="worker_interrupted")
    due = (
        KnowledgeSourceSync.all_objects.filter(enabled=True, next_run_at__lte=now)
        .exclude(status="running")
        .order_by("next_run_at", "pk")
    )
    for wid, pk in due.values_list("workspace_id", "pk")[:50]:
        enqueue_once(refresh_source, wid, pk)


@shared_task(ignore_result=True, soft_time_limit=240, time_limit=270)
@pause_guard("ai")
def refresh_source(workspace_id, sync_id):
    with transaction.atomic():
        row = (
            KnowledgeSourceSync.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=sync_id, enabled=True, next_run_at__lte=timezone.now())
            .exclude(status="running")
            .first()
        )
        if not row:
            return
        lease = uuid.uuid4()
        row.status, row.started_at, row.lease_token = "running", timezone.now(), lease
        row.save()
        integration_id = row.integration_id
    error, source, config = "", None, None
    try:
        check_feature(workspace_id, "integrations_unlocked")
        check_feature(workspace_id, "ai_agent_enabled")
        config = IntegrationConfig.objects.for_workspace(workspace_id).get(pk=integration_id)
        if not config.enabled or config.status != "active":
            error = "integration_unavailable"
        else:
            source = source_text(config)
    except PlanLimitExceeded:
        error = "plan_limit"
    except Exception:
        # Provider bodies and credentials never enter status messages.
        error = "source_fetch_failed"
    with transaction.atomic():
        row = (
            KnowledgeSourceSync.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=sync_id, enabled=True, lease_token=lease, status="running")
            .first()
        )
        if not row:
            return
        if not error:
            try:
                # Recheck entitlements after fetching in case of a concurrent downgrade.
                check_feature(workspace_id, "integrations_unlocked")
                check_feature(workspace_id, "ai_agent_enabled")
                store_snapshot(config, source)
            except PlanLimitExceeded:
                error = "plan_limit"
            except Exception:
                error = "source_changed_or_indexing"
        now = timezone.now()
        row.last_checked_at, row.error_code, row.lease_token = now, error, None
        row.status = "error" if error else "synced"
        if not error:
            row.last_success_at = now
        row.next_run_at = now + timedelta(
            minutes=min(row.interval_minutes, 15) if error else row.interval_minutes
        )
        row.save()
        audit(row.workspace, None, "knowledge.sync_failed" if error else "knowledge.synced", row.pk)
