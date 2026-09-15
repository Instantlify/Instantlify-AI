from celery import shared_task
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from .dispatch import enqueue_once
from .models import AuditEvent, OutboxEvent


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
