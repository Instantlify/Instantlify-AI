import base64
import json
from email import message_from_bytes
from unittest.mock import patch

import pytest

from apps.crm.integrations import CRMIntegration
from apps.crm.models import IntegrationConfig
from tests.conftest import set_limits

pytestmark = pytest.mark.django_db


def test_live_gmail_without_google_app_returns_actionable_setup_error(client, workspace, settings):
    from apps.channels.models import OAuthState

    set_limits(workspace, integrations_unlocked=True)
    settings.CHANNEL_ADAPTER_MODE = "live"
    settings.GOOGLE_CLIENT_ID = ""
    settings.GOOGLE_CLIENT_SECRET = ""
    response = client.post(
        f"/api/workspaces/{workspace.pk}/integrations/gmail/oauth/", {}, format="json"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "integration_oauth_not_configured"
    assert "Google OAuth app" in response.json()["detail"]
    assert "AI provider API key" in response.json()["detail"]
    assert not OAuthState.all_objects.exists()
    assert not IntegrationConfig.objects.for_workspace(workspace).exists()


def test_secret_updates_keep_other_saved_secrets_and_destination_options(client, workspace):
    set_limits(workspace, integrations_unlocked=True)
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="google_calendar",
        credentials=json.dumps({"access_token": "old", "refresh_token": "keep-private"}),
        options={"calendar_id": "team"},
    )
    response = client.post(
        f"/api/workspaces/{workspace.pk}/integrations/",
        {"provider": "google_calendar", "credentials": {"access_token": "new"}, "options": {}},
        format="json",
    )
    assert response.status_code == 201
    config.refresh_from_db()
    assert json.loads(config.credentials) == {
        "access_token": "new",
        "refresh_token": "keep-private",
    }
    assert config.options == {"calendar_id": "team"}
    assert "keep-private" not in response.content.decode()
    assert "credentials" not in response.json()


def test_public_options_cannot_expose_provider_secrets(client, workspace):
    response = client.post(
        f"/api/workspaces/{workspace.pk}/integrations/",
        {
            "provider": "slack",
            "credentials": {"access_token": "secret"},
            "options": {"access_token": "secret"},
        },
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "provider,options",
    [("google_sheets", {"spreadsheet_id": "sheet-one", "range": "Leads!A:C"}), ("gmail", {})],
)
def test_new_google_hosted_flows_keep_destinations_and_reject_oauth_replay(
    client, workspace, settings, provider, options
):
    set_limits(workspace, integrations_unlocked=True)
    settings.GOOGLE_CLIENT_ID = ""
    settings.GOOGLE_CLIENT_SECRET = ""
    started = client.post(
        f"/api/workspaces/{workspace.pk}/integrations/{provider}/oauth/",
        {"options": options},
        format="json",
    )
    assert started.status_code == 200
    url = started.json()["authorization_url"]
    assert client.get(url).status_code == 302
    assert client.get(url).status_code == 400
    config = IntegrationConfig.objects.for_workspace(workspace).get(provider=provider)
    assert config.options == options
    assert config.is_test and config.enabled
    result = client.get(f"/api/workspaces/{workspace.pk}/integrations/").json()["results"]
    assert next(item for item in result if item["provider"] == provider)["configured"] is True


def test_oauth_destination_options_cannot_store_secrets(client, workspace):
    set_limits(workspace, integrations_unlocked=True)
    response = client.post(
        f"/api/workspaces/{workspace.pk}/integrations/google_sheets/oauth/",
        {"options": {"access_token": "not-public"}},
        format="json",
    )
    assert response.status_code == 400
    assert not IntegrationConfig.objects.for_workspace(workspace).exists()


def test_sheet_append_uses_raw_values_and_encoded_destination(workspace):
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="google_sheets",
        credentials=json.dumps({"access_token": "token"}),
        options={"spreadsheet_id": "sheet-one", "range": "Leads!A:C"},
    )
    with patch(
        "apps.crm.integrations.request", return_value={"updates": {"updatedRows": 1}}
    ) as send:
        result = CRMIntegration(config).execute(
            "sync_lead",
            {"name": "=IMPORTXML(unsafe)", "email": "lead@example.com", "stage": "qualified"},
            "stable",
        )
    assert result["updates"]["updatedRows"] == 1
    assert send.call_args.args[1].endswith("/sheet-one/values/Leads%21A%3AC:append")
    assert send.call_args.kwargs["params"]["valueInputOption"] == "RAW"
    assert send.call_args.kwargs["json"]["values"][0][0] == "=IMPORTXML(unsafe)"
    assert send.call_args.kwargs["headers"]["Authorization"] == "Bearer token"


def test_gmail_sends_mime_with_sender_and_recipient_without_header_injection(workspace):
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="gmail",
        credentials=json.dumps({"access_token": "token"}),
        options={"sender_email": "team@example.com"},
    )
    adapter = CRMIntegration(config)
    with patch("apps.crm.integrations.request", return_value={"id": "mail-one"}) as send:
        assert adapter.execute(
            "send_email",
            {"to": "lead@example.com", "subject": "Your guide", "text": "Here it is"},
            "stable",
        ) == {"id": "mail-one"}
    message = message_from_bytes(base64.urlsafe_b64decode(send.call_args.kwargs["json"]["raw"]))
    assert message["To"] == "lead@example.com"
    assert message["From"] == "team@example.com"
    assert message["Subject"] == "Your guide"
    with patch("apps.crm.integrations.request") as send, pytest.raises(ValueError):
        adapter.execute(
            "send_email",
            {"to": "lead@example.com", "subject": "Hello\nBcc: other@example.com", "text": "Body"},
            "bad",
        )
    send.assert_not_called()


def test_gmail_oauth_resolves_the_verified_sender_identity(settings):
    from apps.crm.oauth import exchange

    settings.GOOGLE_CLIENT_ID = "client"
    settings.GOOGLE_CLIENT_SECRET = "secret"
    with patch(
        "apps.crm.oauth.request",
        side_effect=[
            {"access_token": "token", "refresh_token": "refresh", "expires_in": 3600},
            {"email": "team@example.com", "email_verified": True},
        ],
    ):
        credentials, options = exchange("gmail", "code")
    assert credentials["access_token"] == "token"
    assert options == {"sender_email": "team@example.com"}
