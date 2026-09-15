import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
from apps.channels.tasks import process_webhook, send_delivery
from apps.channels.transport import AmbiguousDelivery, RetryableError
from apps.crm.models import Message
from apps.crm.services import queue_reply

pytestmark = pytest.mark.django_db


@pytest.fixture
def channel(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id="ig-account",
        display_name="Test",
        access_token="secret",
        expires_at=timezone.now() + timedelta(days=60),
        is_test=True,
    )


def body():
    return json.dumps(
        {
            "entry": [
                {
                    "id": "ig-account",
                    "messaging": [
                        {
                            "sender": {"id": "lead-1"},
                            "message": {"mid": "message-1", "text": "Hello"},
                        }
                    ],
                }
            ]
        }
    ).encode()


@override_settings(META_APP_SECRET="app-secret")
def test_signed_webhook_dedupes_durably_without_broker(channel):
    data = body()
    signature = "sha256=" + hmac.new(b"app-secret", data, hashlib.sha256).hexdigest()
    client = Client()
    assert (
        client.post("/webhooks/instagram/", data, content_type="application/json").status_code
        == 403
    )
    for _ in range(2):
        assert (
            client.post(
                "/webhooks/instagram/",
                data,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
            ).status_code
            == 200
        )
    assert WebhookEvent.objects.for_workspace(channel.workspace_id).count() == 1
    event = WebhookEvent.objects.for_workspace(channel.workspace_id).get()
    with patch("apps.crm.services.notify"):
        process_webhook(str(channel.workspace_id), str(event.id))
        process_webhook(str(channel.workspace_id), str(event.id))
    assert Message.objects.for_workspace(channel.workspace_id).count() == 1


def test_send_retry_and_ambiguous_delivery_are_different(channel):
    delivery = Delivery.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        recipient_id="recipient",
        payload=json.dumps({"text": "Hello"}),
        idempotency_key="once",
        available_at=timezone.now(),
    )
    with patch("apps.channels.tasks.adapter_for") as adapter:
        adapter.return_value.send_message.side_effect = RetryableError(60)
        send_delivery(str(channel.workspace_id), str(delivery.id))
    delivery.refresh_from_db()
    assert delivery.status == "pending"
    assert delivery.available_at > timezone.now() + timedelta(seconds=50)
    delivery.available_at = timezone.now()
    delivery.save()
    with patch("apps.channels.tasks.adapter_for") as adapter:
        adapter.return_value.send_message.side_effect = AmbiguousDelivery()
        send_delivery(str(channel.workspace_id), str(delivery.id))
        send_delivery(str(channel.workspace_id), str(delivery.id))
        assert adapter.return_value.send_message.call_count == 1
    delivery.refresh_from_db()
    assert delivery.status == "unknown"


def test_reply_intent_is_idempotent_and_honors_opt_out(channel):
    from apps.crm.services import receive

    event = WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id="new",
        payload="{}",
        available_at=timezone.now(),
    )
    with patch("apps.crm.services.notify"):
        message = receive(event, {"sender_id": "lead", "text": "hello"})
        first = queue_reply(message.conversation, "hello", "same")
        assert queue_reply(message.conversation, "hello", "same").id == first.id
        lead = message.conversation.identity.lead
        lead.opted_out = True
        lead.save()
        from rest_framework.exceptions import ValidationError

        with pytest.raises(ValidationError):
            queue_reply(message.conversation, "again", "different")
