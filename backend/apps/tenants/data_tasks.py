import json
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from .dispatch import enqueue_once
from .models import DataOperation, Workspace


@shared_task(ignore_result=True)
def dispatch_data_operations():
    for wid, pk in DataOperation.all_objects.filter(status="pending").values_list(
        "workspace_id", "pk"
    )[:10]:
        enqueue_once(process_data_operation, wid, pk, ttl=150)


@shared_task(ignore_result=True, soft_time_limit=100, time_limit=120)
def process_data_operation(workspace_id, operation_id):
    try:
        run_data_operation(workspace_id, operation_id)
    except Exception as exc:
        # The work rolled back; fail visibly instead of re-running a heavy export forever.
        DataOperation.objects.for_workspace(workspace_id).filter(
            pk=operation_id, status="pending"
        ).update(status="failed", error_code=type(exc).__name__[:50])
        logging.getLogger(__name__).warning(
            "Data operation failed", extra={"event_code": "data_operation_failed"}
        )


def run_data_operation(workspace_id, operation_id):
    from apps.agents.models import KnowledgeDocument, UsageRecord
    from apps.automations.models import Automation
    from apps.billing.models import BillingAccount
    from apps.crm.models import ChannelIdentity, Conversation, InternalNote, Lead, Message

    from .models import AuditEvent

    with transaction.atomic():
        job = (
            DataOperation.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=operation_id, status="pending")
            .first()
        )
        if not job:
            return
        if job.kind == "delete":
            account = BillingAccount.objects.for_workspace(workspace_id).first()
            if (
                account
                and account.subscription_id
                and account.status not in {"canceled", "incomplete_expired"}
            ):
                job.status = "failed"
                job.error_code = "cancel_subscription_first"
                job.save()
                return
            Workspace.objects.get(pk=workspace_id).delete()
            return
        tables = {
            "leads": (
                Lead,
                ["id", "name", "email", "stage", "tags", "fields", "opted_out", "created_at"],
            ),
            "identities": (ChannelIdentity, ["id", "lead_id", "connection_id", "external_id"]),
            "conversations": (Conversation, ["id", "identity_id", "assigned_to_id", "status"]),
            "messages": (
                Message,
                ["id", "conversation_id", "direction", "text", "kind", "created_at"],
            ),
            "notes": (InternalNote, ["id", "conversation_id", "author_id", "text", "created_at"]),
            "automations": (
                Automation,
                ["id", "name", "draft", "published", "revision", "enabled"],
            ),
            "knowledge": (KnowledgeDocument, ["id", "title", "source", "file_type"]),
            "usage": (
                UsageRecord,
                ["id", "model", "kind", "input_tokens", "output_tokens", "cost", "created_at"],
            ),
            "audit": (
                AuditEvent,
                ["id", "action", "actor_id", "target_id", "metadata", "created_at"],
            ),
        }
        result = {
            name: list(model.objects.for_workspace(workspace_id).values(*fields))
            for name, (model, fields) in tables.items()
        }
        job.result = json.dumps(result, cls=DjangoJSONEncoder)
        job.status = "complete"
        job.save()


@shared_task(ignore_result=True)
def apply_retention():
    from apps.agents.models import AgentRun, ToolCall, VoiceAsset
    from apps.channels.models import Delivery, WebhookEvent
    from apps.crm.models import InternalNote, Message

    cutoff = timezone.now() - timedelta(days=settings.RETENTION_DAYS)
    # Keep delivery/event dedupe tombstones while removing their customer payloads.
    for model, field in [
        (WebhookEvent, "payload"),
        (Delivery, "payload"),
        (ToolCall, "input"),
        (ToolCall, "output"),
        (AgentRun, "checkpoint"),
    ]:
        model.all_objects.filter(created_at__lt=cutoff).update(**{field: "{}"})
    Message.all_objects.filter(created_at__lt=cutoff).update(text="", attachments="[]")
    InternalNote.all_objects.filter(created_at__lt=cutoff).update(text="")
    VoiceAsset.all_objects.filter(created_at__lt=timezone.now() - timedelta(hours=2)).delete()
    DataOperation.all_objects.filter(
        created_at__lt=timezone.now() - timedelta(days=1), kind="export"
    ).delete()
