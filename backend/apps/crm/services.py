import json
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.channels.adapters import WINDOWED_PROVIDERS
from apps.channels.models import Delivery
from apps.tenants.services import audit

from .models import ChannelIdentity, Conversation, Lead, Message


def notify(workspace_id):
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    try:
        async_to_sync(get_channel_layer().group_send)(
            f"workspace.{workspace_id}", {"type": "workspace.changed"}
        )
    except Exception:
        # Realtime notifications are hints; durable API state remains authoritative.
        pass


# Wait briefly so a burst of messages is classified once, with its full context.
SEGMENT_DELAY = timedelta(seconds=60)


@transaction.atomic
def receive(event, payload):
    if Message.objects.for_workspace(event.workspace_id).filter(event=event).exists():
        return
    identity = (
        ChannelIdentity.objects.for_workspace(event.workspace_id)
        .filter(connection=event.connection, external_id=payload["sender_id"])
        .first()
    )
    if not identity:
        # Serialize first-contact creation on the connection, avoiding orphan leads.
        type(event.connection).objects.for_workspace(event.workspace_id).select_for_update().get(
            pk=event.connection_id
        )
        identity = (
            ChannelIdentity.objects.for_workspace(event.workspace_id)
            .filter(connection=event.connection, external_id=payload["sender_id"])
            .first()
        )
        if not identity:
            lead = Lead.objects.for_workspace(event.workspace_id).create(
                workspace_id=event.workspace_id, name=payload["sender_id"]
            )
            identity = ChannelIdentity.objects.for_workspace(event.workspace_id).create(
                workspace_id=event.workspace_id,
                connection=event.connection,
                external_id=payload["sender_id"],
                lead=lead,
            )
            from apps.public_api.services import emit, lead_payload

            emit(event.workspace_id, "lead.created", lead_payload(lead))
    conversation, _ = Conversation.objects.for_workspace(event.workspace_id).get_or_create(
        identity=identity, defaults={"workspace_id": event.workspace_id}
    )
    conversation = (
        Conversation.objects.for_workspace(event.workspace_id)
        .select_for_update()
        .get(pk=conversation.pk)
    )
    conversation.last_inbound_at = timezone.now()
    conversation.save()
    msg = Message.objects.for_workspace(event.workspace_id).create(
        workspace_id=event.workspace_id,
        conversation=conversation,
        event=event,
        direction="inbound",
        text=payload.get("text", "")[:10000],
        kind=payload.get("kind", "dm"),
        attachments=json.dumps(payload.get("attachments", [])),
    )
    from apps.analytics.services import record
    from apps.public_api.services import emit, message_payload

    emit(event.workspace_id, "message.received", message_payload(msg))
    record(
        event.workspace_id,
        "comment" if msg.kind in {"comment", "live_comment"} else "dm",
        key=f"inbound:{msg.id}",
        provider=event.connection.provider,
        lead_id=identity.lead_id,
        conversation_id=conversation.pk,
    )
    if not msg.text and has_voice(payload.get("attachments")):
        # Voice notes are transcribed by a worker, then routed exactly like typed text.
        msg.transcription_status = "pending"
        msg.save(update_fields=["transcription_status"])
    else:
        handle_inbound(msg, identity.lead, payload)
    transaction.on_commit(lambda: notify(event.workspace_id))
    return msg


def has_voice(attachments):
    return any(
        isinstance(item, dict) and item.get("type") in {"audio", "voice"}
        for item in attachments or []
    )


def handle_inbound(msg, lead, payload):
    """Opt-out, segmentation scheduling and automation/agent routing for inbound text.
    Callers hold the conversation row lock inside a transaction."""
    from apps.automations.services import route_message

    conversation = msg.conversation
    if msg.text.strip().lower() in {"stop", "unsubscribe", "cancel subscription"}:
        lead.opted_out = True
        lead.save(update_fields=["opted_out"])
        conversation.ai_enabled = False
        conversation.save()
    if lead.opted_out:
        return
    Lead.objects.for_workspace(msg.workspace_id).filter(
        pk=lead.pk, segment_due_at__isnull=True
    ).update(segment_due_at=timezone.now() + SEGMENT_DELAY)
    route_message(msg, payload)


@transaction.atomic
def queue_reply(
    conversation, text, key, *, actor=None, buttons=None, private_reply_id=None, media_url=None
):
    existing = (
        Delivery.objects.for_workspace(conversation.workspace_id)
        .filter(idempotency_key=key)
        .first()
    )
    if existing:
        return existing
    conversation = (
        Conversation.objects.for_workspace(conversation.workspace_id)
        .select_for_update()
        .select_related("identity__lead", "identity__connection")
        .get(pk=conversation.pk)
    )
    if conversation.identity.lead.opted_out:
        raise ValidationError("This lead has opted out.")
    connection = conversation.identity.connection
    if (
        connection.provider in WINDOWED_PROVIDERS
        and not private_reply_id
        and (
            not conversation.last_inbound_at
            or conversation.last_inbound_at < timezone.now() - timedelta(hours=24)
        )
    ):
        raise ValidationError("The messaging window has closed. Wait for a new customer message.")
    if not text and not media_url:
        raise ValidationError("A message is required.")
    when = max(
        timezone.now(), (conversation.last_outbound_at or timezone.now()) + timedelta(seconds=5)
    )
    payload = {
        "text": text[:2000],
        "buttons": buttons or [],
        "private_reply": bool(private_reply_id),
    }
    if media_url:
        payload.update(kind="voice", media_url=media_url)
    item = Delivery.objects.for_workspace(conversation.workspace_id).create(
        workspace_id=conversation.workspace_id,
        connection=connection,
        recipient_id=private_reply_id or conversation.identity.external_id,
        idempotency_key=key,
        payload=json.dumps(payload),
        available_at=when,
    )
    Message.objects.for_workspace(conversation.workspace_id).create(
        workspace_id=conversation.workspace_id,
        conversation=conversation,
        direction="outbound",
        text=text[:2000],
        delivery=item,
        kind="voice" if media_url else "text",
    )
    conversation.last_outbound_at = when
    conversation.save()
    audit(conversation.workspace, actor, "message.queued", item.id)
    from apps.analytics.services import attribution, record

    record(
        conversation.workspace_id,
        "replied",
        key=f"replied:{item.id}",
        provider=connection.provider,
        lead_id=conversation.identity.lead_id,
        conversation_id=conversation.pk,
        **attribution(conversation),
    )
    transaction.on_commit(lambda: notify(conversation.workspace_id))
    return item
