import json
from unittest.mock import patch

import pytest

from apps.channels.transport import ProviderError, RetryableError
from apps.crm.models import IntegrationConfig

pytestmark = pytest.mark.django_db


def integration(workspace, provider, credentials, options=None, is_test=False):
    return IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider=provider,
        credentials=json.dumps(credentials),
        options=options or {},
        is_test=is_test,
        enabled=True,
    )


def endpoint(workspace, item):
    return f"/api/workspaces/{workspace.pk}/integrations/{item.pk}/test/"


def test_valid_key_is_reported_connected(client, workspace, settings):
    settings.CHANNEL_ADAPTER_MODE = "live"
    item = integration(
        workspace, "airtable", {"api_key": "pat-123"}, {"base_id": "b", "table_id": "t"}
    )
    with patch("apps.crm.connection_test.request", return_value={"id": "usr1"}) as call:
        res = client.post(endpoint(workspace, item))
    assert res.json()["ok"] is True
    method, url = call.call_args.args
    assert (method, url) == ("GET", "https://api.airtable.com/v0/meta/whoami")
    assert call.call_args.kwargs["headers"]["Authorization"] == "Bearer pat-123"
    assert "pat-123" not in res.content.decode()


@pytest.mark.parametrize(
    "error,detail",
    [
        (ProviderError("invalid_api_key"), "rejected this API key"),
        (ProviderError("provider_rejected"), "rejected these credentials"),
        (RetryableError(30), "did not respond"),
    ],
)
def test_failures_are_explained(client, workspace, settings, error, detail):
    settings.CHANNEL_ADAPTER_MODE = "live"
    item = integration(workspace, "elevenlabs", {"api_key": "bad"})
    with patch("apps.crm.connection_test.request", side_effect=error):
        body = client.post(endpoint(workspace, item)).json()
    assert body["ok"] is False and detail in body["detail"]


def test_slack_ok_false_and_unsupported_and_test_mode(client, workspace, settings):
    settings.CHANNEL_ADAPTER_MODE = "live"
    slack = integration(workspace, "slack", {"access_token": "x"}, {"channel_id": "C1"})
    with patch("apps.crm.connection_test.request", return_value={"ok": False}):
        assert client.post(endpoint(workspace, slack)).json()["ok"] is False
    other = integration(workspace, "n8n", {"webhook_url": "https://n8n.example.com/h"})
    assert client.post(endpoint(workspace, other)).json()["ok"] is None
    fake = integration(workspace, "airtable", {"api_key": "x"}, is_test=True)
    with patch("apps.crm.connection_test.request") as call:
        assert client.post(endpoint(workspace, fake)).json()["ok"] is True
    call.assert_not_called()
