from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from .dispatch import enqueue_once
from .models import AuditEvent, Membership, OutboxEvent


@shared_task(ignore_result=True)
def dispatch_outbox():
    # Intentional cross-tenant operational fan-out; only IDs enter Redis.
    pending = OutboxEvent.all_objects.filter(processed_at__isnull=True).values_list(
        "workspace_id", "id"
    )[:100]
    for workspace_id, event_id in pending:
        enqueue_once(process_outbox, workspace_id, event_id)


@shared_task(ignore_result=True, autoretry_for=(OSError,), retry_backoff=True, max_retries=5)
def process_outbox(workspace_id, event_id):
    with transaction.atomic():
        event = (
            OutboxEvent.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=event_id)
            .first()
        )
        if not event or event.processed_at:
            return
        if event.kind != "workspace.created":
            raise ValueError("Unsupported outbox event")
        AuditEvent.objects.for_workspace(workspace_id).create(
            workspace_id=workspace_id,
            action="workspace.provisioned",
            target_id=str(event.workspace_id),
        )
        event.processed_at = timezone.now()
        event.save(update_fields=["processed_at"])


@shared_task(ignore_result=True)
def expire_tokens():
    call_command("flushexpiredtokens")


@shared_task(ignore_result=True)
def purge_unverified_signups():
    """Release addresses claimed but never confirmed.

    Email is unique, so an unconfirmed signup holds that address against the person who
    actually owns it. Only accounts that never confirmed, never joined a workspace and
    are past the window go; anything with a membership is somebody's real account and
    is left alone whatever its verification state.
    """
    cutoff = timezone.now() - timedelta(days=settings.UNVERIFIED_SIGNUP_DAYS)
    members = Membership.all_objects.values_list("user_id", flat=True)
    stale = get_user_model().objects.filter(
        email_verified_at__isnull=True,
        date_joined__lt=cutoff,
        is_staff=False,
        is_superuser=False,
    )
    return stale.exclude(pk__in=members).delete()[0]
