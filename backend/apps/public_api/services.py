import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from .models import EVENTS, OutboundWebhook, WebhookSubscription


def emit(workspace_id, event, data):
    """Queue an outbound webhook for every active subscription to `event`.

    Called inside the transaction that produced the fact, so a rollback never leaks."""
    if event not in EVENTS:
        raise ValueError("unknown_event")
    # Membership is checked in Python: JSON containment is PostgreSQL-only and the
    # per-workspace subscription list is tiny.
    subscriptions = [
        item
        for item in WebhookSubscription.objects.for_workspace(workspace_id).filter(active=True)
        if event in item.events
    ]
    body = json.dumps(
        {
            "event": event,
            "workspace_id": str(workspace_id),
            "occurred_at": timezone.now().isoformat(),
            "data": data,
        },
        cls=DjangoJSONEncoder,
    )
    for subscription in subscriptions:
        OutboundWebhook.objects.for_workspace(workspace_id).create(
            workspace_id=workspace_id,
            subscription=subscription,
            event=event,
            payload=body,
            available_at=timezone.now(),
        )


def lead_payload(lead):
    return {
        "id": str(lead.id),
        "name": lead.name,
        "email": lead.email,
        "stage": lead.stage,
        "tags": lead.tags,
        "fields": lead.fields,
        "opted_out": lead.opted_out,
        "created_at": lead.created_at,
    }


def conversation_payload(conversation):
    return {
        "id": str(conversation.id),
        "lead_id": str(conversation.identity.lead_id),
        "provider": conversation.identity.connection.provider,
        "status": conversation.status,
        "assigned_to": conversation.assigned_to_id,
        "ai_enabled": conversation.ai_enabled,
        "last_inbound_at": conversation.last_inbound_at,
    }


def message_payload(message):
    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "direction": message.direction,
        "kind": message.kind,
        "text": message.text,
        "created_at": message.created_at,
    }
