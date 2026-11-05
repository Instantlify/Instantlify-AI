from contextlib import contextmanager
from unittest.mock import patch

import pytest
from django.db import connection as database
from rest_framework.test import APIClient

from apps.channels.models import ChannelConnection
from apps.channels.transport import ProviderError
from apps.tenants.models import Membership, User
from apps.tenants.services import create_workspace
from tests.conftest import set_limits

pytestmark = pytest.mark.django_db
TOKEN = "123456789:example-token-for-tests"
PROFILE = {"id": 123456789, "is_bot": True, "first_name": "Nemio Bot", "username": "nemio_test_bot"}


@pytest.fixture(autouse=True)
def live_telegram(settings):
    settings.CHANNEL_ADAPTER_MODE = "live"
    settings.PUBLIC_APP_URL = "https://nemio.example"


@contextmanager
def telegram():
    with (
        patch(
            "apps.channels.telegram_connect.TelegramAdapter.call", return_value=PROFILE
        ) as verify,
        patch(
            "apps.channels.telegram_connect.TelegramAdapter.configure_webhook", return_value=True
        ) as webhook,
    ):
        yield verify, webhook


def url(workspace):
    return f"/api/workspaces/{workspace.pk}/telegram/connect/"


def test_token_only_connection_autofills_bot_and_encrypts_token(client, workspace):
    with telegram() as (verify, webhook):
        response = client.post(url(workspace), {"access_token": TOKEN}, format="json")
    assert response.status_code == 200, response.content
    verify.assert_called_once_with("getMe", {})
    item = ChannelConnection.objects.for_workspace(workspace).get()
    assert item.external_account_id == "123456789"
    assert item.display_name == "Nemio Bot"
    assert item.status == "active" and item.is_test is False
    webhook.assert_called_once_with(f"https://nemio.example/webhooks/telegram/{item.pk}/")
    assert TOKEN not in response.content.decode()
    with database.cursor() as cursor:
        cursor.execute(
            "SELECT access_token FROM channels_channelconnection WHERE id=%s",
            [item.pk.hex if database.vendor == "sqlite" else item.pk],
        )
        assert cursor.fetchone()[0] != TOKEN


def test_reconnect_at_plan_limit_reuses_connection(client, workspace):
    set_limits(workspace, max_instagram_accounts=1)
    with telegram():
        first = client.post(url(workspace), {"access_token": TOKEN}, format="json")
        second = client.post(url(workspace), {"access_token": TOKEN}, format="json")
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert ChannelConnection.objects.for_workspace(workspace).count() == 1


def test_invalid_token_is_not_saved(client, workspace):
    with patch(
        "apps.channels.telegram_connect.TelegramAdapter.call",
        side_effect=ProviderError("credentials_expired"),
    ):
        response = client.post(url(workspace), {"access_token": TOKEN}, format="json")
    assert response.status_code == 400
    assert not ChannelConnection.objects.for_workspace(workspace).exists()
    assert TOKEN not in response.content.decode()


def test_webhook_failure_is_retryable_without_duplicate(client, workspace):
    with telegram() as (_, webhook):
        webhook.side_effect = ProviderError()
        response = client.post(url(workspace), {"access_token": TOKEN}, format="json")
    assert response.status_code == 400
    item = ChannelConnection.objects.for_workspace(workspace).get()
    assert item.status == "reconnect_required"
    with telegram():
        retry = client.post(url(workspace), {"access_token": TOKEN}, format="json")
    assert retry.status_code == 200
    assert retry.json()["id"] == str(item.pk)


def test_other_workspace_bot_cannot_be_taken_over(client, workspace, user):
    with telegram():
        assert (
            client.post(url(workspace), {"access_token": TOKEN}, format="json").status_code == 200
        )
    other = create_workspace(user, "Other")
    with telegram() as (_, webhook):
        response = client.post(url(other), {"access_token": TOKEN}, format="json")
    assert response.status_code == 400
    webhook.assert_not_called()
    assert not ChannelConnection.objects.for_workspace(other).exists()


def test_https_configuration_checked_before_token_use(client, workspace, settings):
    settings.PUBLIC_APP_URL = "http://localhost:3000"
    with telegram() as (verify, webhook):
        response = client.post(url(workspace), {"access_token": TOKEN}, format="json")
    assert response.status_code == 400
    assert "HTTPS" in response.content.decode()
    verify.assert_not_called()
    webhook.assert_not_called()


def test_agent_cannot_connect_bot(workspace):
    agent = User.objects.create_user(username="telegram-agent", email="tg-agent@example.com")
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=agent, role="agent"
    )
    client = APIClient()
    client.force_authenticate(agent)
    with telegram() as (verify, _):
        assert (
            client.post(url(workspace), {"access_token": TOKEN}, format="json").status_code == 403
        )
    verify.assert_not_called()
