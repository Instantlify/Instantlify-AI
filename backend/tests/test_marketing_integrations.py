import json
from unittest.mock import patch

import httpx
import pytest

from apps.channels.transport import AmbiguousDelivery, _request
from apps.crm.integrations import CRMIntegration
from apps.crm.models import IntegrationConfig

pytestmark = pytest.mark.django_db


def integration(workspace, provider, **options):
    return IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider=provider,
        credentials=json.dumps({"api_key": "private-token"}),
        options=options,
    )


def test_mailerlite_maps_contact_and_never_resubscribes(workspace):
    config = integration(workspace, "mailerlite", group_id="12345")
    with patch(
        "apps.crm.integrations.request",
        return_value={"data": {"id": "one", "status": "unsubscribed"}},
    ) as send:
        result = CRMIntegration(config).execute(
            "sync_lead", {"email": "a@example.com", "name": "A Person"}, "key"
        )
    assert result == {"id": "one", "status": "unsubscribed"}
    assert send.call_args.kwargs["json"] == {
        "email": "a@example.com",
        "fields": {"name": "A Person"},
        "groups": ["12345"],
        "resubscribe": False,
    }


@pytest.mark.parametrize("suppressed", [False, True])
def test_zorromail_uses_idempotency_verified_sender_and_reports_suppression(workspace, suppressed):
    config = integration(
        workspace, "zorromail", sender_email="sender@example.com", sender_name="Our team"
    )
    with patch(
        "apps.crm.integrations.request",
        return_value={
            "id": "mail-one",
            "status": "accepted",
            "suppressedRecipients": ["a@example.com"] if suppressed else [],
        },
    ) as send:
        result = CRMIntegration(config).execute(
            "send_email",
            {"to": "a@example.com", "subject": "Your booking", "text": "Your confirmation"},
            "durable-send-one",
        )
    assert send.call_args.args == ("POST", "https://www.zorromail.app/tx/v1/messages")
    assert send.call_args.kwargs["side_effect"] is True
    assert send.call_args.kwargs["headers"]["Idempotency-Key"] == "durable-send-one"
    assert send.call_args.kwargs["json"] == {
        "from": "sender@example.com",
        "fromName": "Our team",
        "to": ["a@example.com"],
        "subject": "Your booking",
        "text": "Your confirmation",
    }
    assert result["suppressed"] is suppressed and result["accepted"] is not suppressed


def test_zorromail_configuration_is_supported_and_secrets_are_not_returned(client, workspace):
    response = client.post(
        f"/api/workspaces/{workspace.pk}/integrations/",
        {
            "provider": "zorromail",
            "credentials": {"api_key": "private-token"},
            "options": {"sender_email": "sender@example.com"},
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert "private-token" not in response.content.decode()
    assert response.json()["options"]["sender_email"] == "sender@example.com"


def test_zorromail_omits_optional_empty_sender_name(workspace):
    config = integration(workspace, "zorromail", sender_email="sender@example.com")
    with patch("apps.crm.integrations.request", return_value={"id": "mail-one"}) as send:
        CRMIntegration(config).execute(
            "send_email", {"to": "a@example.com", "text": "Hello"}, "send-one"
        )
    assert "fromName" not in send.call_args.kwargs["json"]


def test_klaviyo_adds_existing_profile_to_list_without_changing_consent(workspace):
    config = integration(workspace, "klaviyo", list_id="my/list")
    with patch(
        "apps.crm.integrations.request",
        side_effect=[{"data": {"id": "profile-one"}}, {"accepted": True}],
    ) as send:
        result = CRMIntegration(config).execute(
            "sync_lead", {"email": "a@example.com", "name": "A Person"}, "key"
        )
    assert result["marketing_consent_changed"] is False
    assert send.call_args.args[1].endswith("/my%2Flist/relationships/profiles")
    assert send.call_args.kwargs["json"] == {"data": [{"type": "profile", "id": "profile-one"}]}
    assert send.call_args.kwargs["headers"]["Authorization"] == "Klaviyo-API-Key private-token"


def test_outlook_preserves_text_and_returns_accepted_not_delivered(workspace):
    config = integration(workspace, "outlook")
    with patch(
        "apps.crm.integrations.request", return_value={"accepted": True, "status_code": 202}
    ) as send:
        result = CRMIntegration(config).execute(
            "send_email",
            {"to": "a@example.com", "text": "<b>Literal text</b>", "subject": "Hello"},
            "key",
        )
    assert result == {"accepted": True, "operation": "send_email"}
    assert send.call_args.kwargs["json"]["message"]["body"] == {
        "contentType": "Text",
        "content": "<b>Literal text</b>",
    }


def test_empty_success_is_explicit_and_does_not_hide_uncertain_sends():
    with patch("apps.channels.transport.httpx.request", return_value=httpx.Response(202)):
        assert _request("POST", "https://example.com", empty_success=True) == {
            "accepted": True,
            "status_code": 202,
        }
        with pytest.raises(AmbiguousDelivery):
            _request("POST", "https://example.com", side_effect=True)


def test_systeme_preserves_existing_unsubscribe_and_only_creates_missing_contacts(workspace):
    config = integration(workspace, "systeme_io")
    with patch(
        "apps.crm.integrations.request",
        return_value={"items": [{"id": 42, "email": "A@example.com", "unsubscribed": True}]},
    ) as send:
        assert CRMIntegration(config).execute("sync_lead", {"email": "a@example.com"}, "key") == {
            "id": "42",
            "existing": True,
        }
    send.assert_called_once()
    with patch("apps.crm.integrations.request", side_effect=[{"items": []}, {"id": 43}]) as send:
        assert (
            CRMIntegration(config).execute("sync_lead", {"email": "b@example.com"}, "key")["id"]
            == "43"
        )
    assert send.call_args.kwargs["json"] == {"email": "b@example.com"}
