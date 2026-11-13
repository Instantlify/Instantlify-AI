"""Erase verified Meta-linked data; ambiguous or legally sensitive records need review."""

from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.tenants.dispatch import enqueue_once

from .models import ChannelConnection, MetaDataDeletion


@shared_task(ignore_result=True)
def dispatch_meta_deletions():
    MetaDataDeletion.objects.filter(
        status="processing", started_at__lt=timezone.now() - timedelta(minutes=10)
    ).update(status="needs_review", error_code="worker_interrupted")
    for pk in MetaDataDeletion.objects.filter(status="pending").values_list("pk", flat=True)[:10]:
        # The normal tenant dispatcher accepts a workspace argument; these verified
        # requests can cover multiple workspaces, so use a fixed system marker.
        enqueue_once(process_meta_deletion, "meta", pk, ttl=150)


def references(value, identifiers):
    if isinstance(value, str):
        return any(identifier in value for identifier in identifiers)
    if isinstance(value, dict):
        return any(references(item, identifiers) for item in value.values())
    if isinstance(value, list):
        return any(references(item, identifiers) for item in value)
    return False


def erase_connection(connection):
    from apps.agents.models import AgentRun
    from apps.automations.models import ConversationState, WorkflowActionJob
    from apps.billing.models import Payment
    from apps.crm.models import ChannelIdentity, Conversation, IntegrationJob, Lead
    from apps.platform_ops.models import UserSegment
    from apps.public_api.models import OutboundWebhook
    from apps.tenants.models import AuditEvent, DataOperation
    from apps.tools.models import FormSubmission

    from .models import Delivery, WebhookEvent

    wid = connection.workspace_id
    conversations = Conversation.objects.for_workspace(wid).filter(identity__connection=connection)
    # Do not let a CASCADE silently destroy transaction records. An operator must
    # determine the applicable erasure/retention scope for these cases.
    if Payment.objects.for_workspace(wid).filter(conversation__in=conversations).exists():
        return False, True
    if (
        Delivery.objects.for_workspace(wid).filter(connection=connection, status="sending").exists()
        or WebhookEvent.objects.for_workspace(wid)
        .filter(connection=connection, status="processing")
        .exists()
        or AgentRun.objects.for_workspace(wid)
        .filter(message__conversation__in=conversations, status="running")
        .exists()
        or WorkflowActionJob.objects.for_workspace(wid)
        .filter(
            state__conversation__in=conversations,
            status__in=["executing", "calling", "rendering", "polling"],
        )
        .exists()
    ):
        return False, True
    if conversations.count() > 5000:
        return False, True
    lead_ids = list(
        ChannelIdentity.objects.for_workspace(wid)
        .filter(connection=connection)
        .values_list("lead_id", flat=True)
    )
    identifiers = {
        str(connection.pk),
        *(str(pk) for pk in lead_ids),
        *(str(pk) for pk in conversations.values_list("pk", flat=True)),
        *(
            str(pk)
            for pk in ConversationState.objects.for_workspace(wid)
            .filter(conversation__in=conversations)
            .values_list("pk", flat=True)
        ),
    }
    # Exports are snapshots and can otherwise keep deleted platform content alive.
    DataOperation.objects.for_workspace(wid).filter(kind="export").update(
        result="", status="expired", error_code="meta_data_deleted"
    )
    needs_review = False
    for job in IntegrationJob.objects.for_workspace(wid).iterator():
        if references(job.payload, identifiers) or references(job.result, identifiers):
            if job.status == "executing":
                return False, True
            needs_review = needs_review or job.status == "complete"
            job.payload, job.result, job.status = "{}", "{}", "needs_review"
            job.save(update_fields=["payload", "result", "status"])
    for hook in OutboundWebhook.objects.for_workspace(wid).iterator():
        if references(hook.payload, identifiers):
            if hook.status == "sending":
                return False, True
            needs_review = needs_review or hook.status == "sent"
            hook.payload, hook.status = "{}", "failed"
            hook.save(update_fields=["payload", "status"])
    for event in AuditEvent.objects.for_workspace(wid).iterator():
        if str(event.target_id) in identifiers or references(event.metadata, identifiers):
            event.metadata, event.target_id = {}, ""
            event.save(update_fields=["metadata", "target_id"])
    UserSegment.objects.filter(connection_id=connection.pk).delete()
    connection.delete()  # identities, conversations, messages, events, deliveries and derived runs
    for lead in Lead.objects.for_workspace(wid).select_for_update().filter(pk__in=lead_ids):
        if (
            ChannelIdentity.objects.for_workspace(wid).filter(lead=lead).exists()
            or FormSubmission.objects.for_workspace(wid).filter(lead=lead).exists()
            or Payment.objects.for_workspace(wid).filter(lead=lead).exists()
        ):
            # Profiles/notes/fields shared with an independent source need a human
            # provenance check; do not erase another channel's records blindly.
            lead.ai_summary, lead.ai_summary_at = "", None
            lead.save(update_fields=["ai_summary", "ai_summary_at"])
            needs_review = True
        else:
            lead.delete()
    return True, needs_review


@shared_task(ignore_result=True, soft_time_limit=100, time_limit=120)
def process_meta_deletion(_system, request_id):
    with transaction.atomic():
        record = (
            MetaDataDeletion.objects.select_for_update()
            .filter(pk=request_id, status="pending")
            .first()
        )
        if not record:
            return
        record.status, record.started_at = "processing", timezone.now()
        record.save(update_fields=["status", "started_at"])
    try:
        with transaction.atomic():
            record = MetaDataDeletion.objects.select_for_update().get(pk=request_id)
            if record.status != "processing":
                return
            if not record.connection_ids or not record.subject_id:
                record.status, record.error_code = "needs_review", "identity_mapping_required"
            else:
                connections = list(
                    ChannelConnection.all_objects.select_for_update().filter(
                        pk__in=record.connection_ids
                    )
                )
                review = len(connections) != len(record.connection_ids)
                for connection in connections:
                    from .meta_callbacks import matching_connections

                    if (
                        connection.status != "disconnected"
                        or connection.access_token
                        or not matching_connections(record.subject_id, record.providers)
                        .filter(pk=connection.pk)
                        .exists()
                    ):
                        review = True
                        continue
                    erased, flagged = erase_connection(connection)
                    record.connections_deleted += int(erased)
                    review = review or flagged
                record.status = "needs_review" if review else "completed"
                record.error_code = "scope_or_retention_review" if review else ""
                if not review:
                    record.completed_at, record.subject_id = timezone.now(), ""
            record.save()
    except Exception:
        # Do not claim completion on partial rollback, lost workers or unknown scope.
        MetaDataDeletion.objects.filter(pk=request_id, status="processing").update(
            status="needs_review", error_code="erasure_requires_review"
        )
