import json
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.channels.adapters import WINDOWED_PROVIDERS
from apps.channels.models import Delivery
from apps.tenants.services import audit
from apps.tools.shield import moderate_comment

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
        from apps.tenants.models import Workspace

        Workspace.objects.select_for_update().get(pk=event.workspace_id)
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
            from apps.billing.gating import check_within_limit

            check_within_limit(event.workspace_id, "max_contacts")
            lead = Lead.objects.for_workspace(event.workspace_id).create(
                workspace_id=event.workspace_id,
                name=(payload.get("sender_name") or payload["sender_id"])[:150],
                handle=(payload.get("sender_handle") or "")[:150],
                profile_due_at=timezone.now(),
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
        identity=identity,
        defaults={
            "workspace_id": event.workspace_id,
            "assigned_to_id": identity.lead.assigned_to_id,
        },
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
    elif msg.kind in {"comment", "live_comment"} and moderate_comment(msg, payload):
        pass  # a hidden or deleted comment is kept in the inbox but starts nothing
    else:
        handle_inbound(msg, identity.lead, payload)
    if identity.lead.profile_due_at:
        from apps.tenants.dispatch import enqueue_once

        from .tasks import enrich_lead

        lead_pk = identity.lead_id
        transaction.on_commit(lambda: enqueue_once(enrich_lead, event.workspace_id, lead_pk))
    transaction.on_commit(lambda: notify(event.workspace_id))
    return msg


def sync_profile(lead):
    """Pull the person's public profile from the channel they last used. Keeps a name
    the team typed; only replaces one that is still the raw channel ID or blank."""
    from apps.channels.adapters import IntegrationUnavailable, adapter_for

    identities = list(
        ChannelIdentity.objects.for_workspace(lead.workspace_id)
        .filter(lead=lead)
        .select_related("connection")
        .order_by("-created_at")
    )
    profile = {}
    for identity in identities:
        try:
            profile = adapter_for(identity.connection).fetch_profile(identity.external_id) or {}
        except (IntegrationUnavailable, NotImplementedError):
            continue
        if profile:
            break
    external_ids = {identity.external_id for identity in identities}
    if profile.get("name") and (not lead.name or lead.name in external_ids):
        lead.name = str(profile["name"])[:150]
    if profile.get("handle"):
        lead.handle = str(profile["handle"])[:150]
    if profile.get("avatar_url"):
        lead.avatar_url = str(profile["avatar_url"])[:1000]
    lead.profile_synced_at = timezone.now()
    lead.profile_due_at = None
    lead.save(update_fields=["name", "handle", "avatar_url", "profile_synced_at", "profile_due_at"])
    return lead


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
    from .triage import triage_inbound

    triage = triage_inbound(msg)
    if triage.escalate:
        # Before any flow can start or resume: a human answers this one.
        from apps.agents.runtime import HANDOFF_REPLY, hand_off
        from apps.channels.transport import ProviderError

        was_ai = conversation.ai_enabled
        hand_off(conversation, reason=f"triage:{triage.matched}"[:60])
        if was_ai:
            # The customer was talking to the bot and expects an answer; say a person is
            # coming. Flow-only conversations stay quiet until a teammate replies.
            try:
                queue_reply(conversation, HANDOFF_REPLY, f"handoff:{msg.id}")
            except (ValidationError, ProviderError):
                pass  # window closed, paused messaging: the page to the team still stands
        return
    route_message(msg, payload)


def window_closed(connection, conversation):
    """True when the provider's customer-service window no longer permits a free-form DM."""
    closed = connection.provider in WINDOWED_PROVIDERS and (
        not conversation.last_inbound_at
        or conversation.last_inbound_at < timezone.now() - timedelta(hours=24)
    )
    if closed or connection.provider not in {"instagram", "messenger"}:
        return closed
    inbound = Message.objects.for_workspace(conversation.workspace_id).filter(
        conversation=conversation, direction="inbound"
    )
    # Public comments do not open the ordinary Meta DM window. Older imported
    # threads without message history retain their recorded window timestamp.
    if (
        inbound.exclude(kind__in=["comment", "live_comment"])
        .filter(created_at__gte=timezone.now() - timedelta(hours=24))
        .exists()
    ):
        return False
    return inbound.exists()


def private_reply_sent(workspace_id, connection, comment_id, *, exclude=None, in_flight=False):
    """A private reply already exists for this comment. Failed attempts never reached
    the provider, so they do not consume the allowance. With `in_flight`, only attempts
    handed to the provider count, which is what matters at send time."""
    sent = (
        Delivery.objects.for_workspace(workspace_id)
        .filter(connection=connection, recipient_id=comment_id)
        .exclude(message__kind="public_reply")
    )
    sent = (
        sent.filter(status__in=["sending", "sent", "unknown"])
        if in_flight
        else sent.exclude(status="failed")
    )
    if exclude is not None:
        sent = sent.exclude(pk=exclude)
    return sent.exists()


@transaction.atomic
def queue_reply(
    conversation,
    text,
    key,
    *,
    actor=None,
    buttons=None,
    private_reply_id=None,
    media_url=None,
    media_type="voice",
    automation_id=None,
    unless_clicked=None,
    whatsapp_template=None,
):
    from apps.platform_ops.security import assert_enabled

    assert_enabled(conversation.workspace_id, "messaging")
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
    template_payload = None
    if whatsapp_template is not None:
        from apps.channels.whatsapp_templates import prepare_template

        if not actor or whatsapp_template.get("consent_confirmed") is not True:
            raise ValidationError(
                "Confirm the customer's agreement before sending an approved message."
            )
        template_payload, text = prepare_template(connection, whatsapp_template)
    if private_reply_id and private_reply_sent(
        conversation.workspace_id, connection, private_reply_id
    ):
        # Meta allows exactly one private reply per comment. Later steps of the same
        # flow continue in the DM thread, subject to the ordinary window rules.
        private_reply_id = None
    if not template_payload and not private_reply_id and window_closed(connection, conversation):
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
    if template_payload:
        payload.update(kind="whatsapp_template", template_selection=whatsapp_template)
    if automation_id:
        payload["automation_id"] = str(automation_id)
    if unless_clicked:
        payload["unless_clicked"] = unless_clicked
    if media_url:
        if media_type != "voice":
            from apps.channels.media import MEDIA_CHANNELS, validate_media

            validate_media(media_url, media_type)
            if connection.provider not in MEDIA_CHANNELS or private_reply_id:
                raise ValidationError("This channel cannot send this media message.")
        payload.update(
            kind="voice" if media_type == "voice" else "media",
            media_url=media_url,
            media_type=media_type,
        )
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
        text=text[:8192] if template_payload else text[:2000],
        delivery=item,
        kind="template" if template_payload else media_type if media_url else "text",
        attachments=json.dumps([{"type": media_type, "url": media_url}]) if media_url else "[]",
        author=actor,
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
