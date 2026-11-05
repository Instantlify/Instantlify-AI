from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.channels.adapters import FakeChannelAdapter, adapter_for
from apps.channels.models import ChannelConnection
from apps.platform_ops.intelligence import fake_mode

pytestmark = pytest.mark.django_db


def test_simulated_channel_works_in_live_mode_without_platform_keys(client, workspace, settings, user):
    settings.CHANNEL_ADAPTER_MODE = "live"
    settings.ALLOW_TEST_CHANNELS = True
    base = f"/api/workspaces/{workspace.pk}/channels/"
    with patch("httpx.request") as network:
        response = client.post(
            base + "connect/",
            {
                "provider": "instagram",
                "external_account_id": "simulated-ig",
                "display_name": "Test Instagram",
                "is_test": True,
            },
            format="json",
        )
        assert response.status_code == 202, response.content
        connection = ChannelConnection.objects.for_workspace(workspace).get(
            pk=response.json()["id"]
        )
        assert isinstance(adapter_for(connection), FakeChannelAdapter)
        simulated = client.post(
            base + f"{connection.pk}/simulate/",
            {"kind": "dm", "text": "Hello", "sender_id": "customer-1"},
            format="json",
        )
        assert simulated.status_code == 202, simulated.content
        from apps.channels.tasks import process_webhook, send_delivery
        from apps.crm.models import Message
        from apps.crm.services import queue_reply

        process_webhook(str(workspace.pk), simulated.json()["id"])
        inbound = Message.objects.for_workspace(workspace).get(event_id=simulated.json()["id"])
        delivery = queue_reply(inbound.conversation, "Test reply", "test-reply", actor=user)
        delivery.available_at = timezone.now()
        delivery.save(update_fields=["available_at"])
        send_delivery(str(workspace.pk), str(delivery.pk))
        delivery.refresh_from_db()
        assert delivery.status == "sent"
    network.assert_not_called()
    assert fake_mode() is False  # Real platform support AI remains enabled.


@pytest.mark.parametrize("mode,allow", [("live", False), ("disabled", True)])
def test_test_channels_remain_explicitly_gated(client, workspace, settings, mode, allow):
    settings.CHANNEL_ADAPTER_MODE = mode
    settings.ALLOW_TEST_CHANNELS = allow
    response = client.post(
        f"/api/workspaces/{workspace.pk}/channels/connect/",
        {
            "provider": "instagram",
            "external_account_id": "test-ig",
            "display_name": "Test",
            "is_test": True,
        },
        format="json",
    )
    assert response.status_code == 400


def test_test_channel_flag_does_not_enable_real_connections(client, workspace, settings):
    settings.CHANNEL_ADAPTER_MODE = "live"
    settings.ALLOW_TEST_CHANNELS = True
    response = client.post(
        f"/api/workspaces/{workspace.pk}/channels/connect/",
        {
            "provider": "telegram",
            "external_account_id": "real-account",
            "display_name": "Real",
            "is_test": False,
        },
        format="json",
    )
    assert response.status_code == 400
