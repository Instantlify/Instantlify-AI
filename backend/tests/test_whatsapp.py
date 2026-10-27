import copy
import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from conftest import set_limits
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.channels.models import ChannelConnection, Delivery, OAuthState, WebhookEvent
from apps.channels.tasks import process_webhook, send_delivery, verify_connection
from apps.channels.transport import AmbiguousDelivery, ProviderError
from apps.channels.whatsapp_templates import prepare_template, template_definition
from apps.crm.models import ChannelIdentity, Conversation, Lead, Message
from apps.crm.services import queue_reply
from apps.tenants.models import Membership, User
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db

RAW = {
    "id": "700",
    "name": "order_update",
    "language": "en_US",
    "status": "APPROVED",
    "category": "UTILITY",
    "components": [
        {"type": "HEADER", "format": "TEXT", "text": "Order update"},
        {"type": "BODY", "text": "Hello {{1}}, order {{2}} is ready."},
        {"type": "FOOTER", "text": "Thank you"},
        {
            "type": "BUTTONS",
            "buttons": [{"type": "URL", "text": "View order", "url": "https://example.com/{{1}}"}],
        },
    ],
}


@pytest.fixture(autouse=True)
def isolated(settings):
    settings.CHANNEL_ADAPTER_MODE = "live"
    settings.META_APP_ID = "123"
    settings.META_APP_SECRET = "app-secret"
    settings.WHATSAPP_APP_SECRET = "app-secret"
    settings.META_WEBHOOK_VERIFY_TOKEN = "verify-token"
    settings.WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID = "999"
    settings.PUBLIC_APP_URL = "https://nemio.example.com"
    with (
        patch("apps.crm.services.notify"),
        patch("apps.channels.tasks.rate_limit_wait", return_value=0),
    ):
        yield


@pytest.fixture
def connection(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="whatsapp",
        external_account_id="222",
        display_name="Shop",
        access_token="business-secret",
        expires_at=timezone.now() + timedelta(days=90),
        profile={"waba_id": "333"},
        status="active",
    )


@pytest.fixture
def conversation(connection):
    lead = Lead.objects.for_workspace(connection.workspace_id).create(
        workspace_id=connection.workspace_id, name="Customer"
    )
    identity = ChannelIdentity.objects.for_workspace(connection.workspace_id).create(
        workspace_id=connection.workspace_id,
        connection=connection,
        lead=lead,
        external_id="15550101",
    )
    return Conversation.objects.for_workspace(connection.workspace_id).create(
        workspace_id=connection.workspace_id,
        identity=identity,
        last_inbound_at=timezone.now() - timedelta(days=3),
        ai_enabled=False,
    )


def selection(raw=RAW):
    return {
        "name": raw["name"],
        "language": raw["language"],
        "signature": template_definition(raw)["signature"],
        "values": {"body_1": "Alex", "body_2": "A100", "button_0": "A100"},
        "consent_confirmed": True,
    }


def send_now(delivery):
    delivery.available_at = timezone.now()
    delivery.save(update_fields=["available_at"])
    send_delivery(str(delivery.workspace_id), str(delivery.id))


def start(client, workspace):
    result = client.post(f"/api/workspaces/{workspace.id}/whatsapp/connect/", {}, format="json")
    assert result.status_code == 200, result.data
    return result.data


def complete(client, workspace, state, **changes):
    payload = {
        "state": state,
        "code": "one-use-code",
        "waba_id": "333",
        "phone_number_id": "222",
        **changes,
    }
    return client.post(f"/api/workspaces/{workspace.id}/whatsapp/complete/", payload, format="json")


def responses(**debug_changes):
    return [
        {"access_token": "business-secret"},
        {
            "data": {
                "app_id": "123",
                "is_valid": True,
                "scopes": ["whatsapp_business_management", "whatsapp_business_messaging"],
                "granular_scopes": [
                    {"scope": "whatsapp_business_management", "target_ids": ["333"]}
                ],
                **debug_changes,
            }
        },
        {"data": [{"id": "222", "verified_name": "Shop", "display_phone_number": "+1 555 0101"}]},
    ]


def test_setup_reports_missing_configuration_without_secrets(client, workspace, settings):
    settings.META_APP_SECRET = ""
    settings.WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID = ""
    settings.PUBLIC_APP_URL = "http://localhost:3000"
    response = client.get(f"/api/workspaces/{workspace.id}/whatsapp/connect/")
    assert response.status_code == 200 and not response.data["ready"]
    assert len(response.data["steps"]) == 3
    assert "app-secret" not in json.dumps(response.data)
    assert client.post(f"/api/workspaces/{workspace.id}/whatsapp/connect/").status_code == 503
    assert not OAuthState.objects.for_workspace(workspace).exists()


def test_embedded_signup_stores_encrypted_credentials_and_requires_activation(client, workspace):
    prepared = start(client, workspace)
    with patch("apps.channels.whatsapp.graph", side_effect=responses()):
        response = complete(client, workspace, prepared["state"])
    assert response.status_code == 202, response.data
    item = ChannelConnection.objects.for_workspace(workspace).get()
    assert item.status == "setup_required" and item.profile["waba_id"] == "333"
    assert item.access_token == "business-secret" and not item.is_test
    assert "business-secret" not in json.dumps(response.data, default=str)
    assert complete(client, workspace, prepared["state"]).status_code == 400


@pytest.mark.parametrize(
    "change",
    [
        {"app_id": "other-app"},
        {"is_valid": False},
        {"scopes": ["whatsapp_business_management"]},
        {"granular_scopes": [{"scope": "whatsapp_business_management", "target_ids": ["444"]}]},
        {"expires_at": 1},
    ],
)
def test_signup_rejects_unshared_assets_wrong_app_and_expired_grants(client, workspace, change):
    prepared = start(client, workspace)
    with patch("apps.channels.whatsapp.graph", side_effect=responses(**change)):
        response = complete(client, workspace, prepared["state"])
    assert response.status_code == 400
    assert not ChannelConnection.objects.for_workspace(workspace).exists()


def test_signup_rejects_phone_outside_shared_business(client, workspace):
    prepared = start(client, workspace)
    mocked = responses()
    mocked[-1] = {"data": [{"id": "444"}]}
    with patch("apps.channels.whatsapp.graph", side_effect=mocked):
        assert complete(client, workspace, prepared["state"]).status_code == 400


def test_signup_state_is_user_workspace_provider_and_expiry_bound(client, workspace, user):
    prepared = start(client, workspace)
    other = create_workspace(user, "Other")
    assert complete(client, other, prepared["state"]).status_code == 400
    pending = OAuthState.objects.for_workspace(workspace).get()
    pending.expires_at = timezone.now() - timedelta(seconds=1)
    pending.save()
    assert complete(client, workspace, prepared["state"]).status_code == 400


def test_signup_never_moves_another_workspaces_number(client, workspace, user, connection):
    other = create_workspace(user, "Other")
    prepared = start(client, other)
    with patch("apps.channels.whatsapp.graph", side_effect=responses()):
        result = complete(client, other, prepared["state"])
    assert result.status_code == 400
    connection.refresh_from_db()
    assert connection.workspace_id == workspace.id


def test_plan_capacity_and_role_are_enforced_before_signin(client, workspace, connection):
    set_limits(workspace, max_instagram_accounts=1)
    assert client.post(f"/api/workspaces/{workspace.id}/whatsapp/connect/").status_code == 402
    Membership.objects.for_workspace(workspace).update(role="agent")
    assert client.get(f"/api/workspaces/{workspace.id}/whatsapp/connect/").status_code == 403


def test_number_registration_and_subscription_resume_without_repeating_registration(
    client, connection
):
    connection.status = "setup_required"
    connection.save()
    url = f"/api/workspaces/{connection.workspace_id}/whatsapp/{connection.id}/activate/"
    with patch(
        "apps.channels.whatsapp.graph",
        side_effect=[{"data": [{"id": "222"}]}, {"success": True}, ProviderError()],
    ):
        result = client.post(url, {"pin": "123456"}, format="json")
    assert result.status_code == 400
    connection.refresh_from_db()
    assert connection.profile["registered"] is True and connection.status == "setup_required"
    with patch(
        "apps.channels.whatsapp.graph", side_effect=[{"data": [{"id": "222"}]}, {"success": True}]
    ) as graph:
        result = client.post(url, {}, format="json")
    assert result.status_code == 200
    assert all("/register" not in call.args[1] for call in graph.call_args_list)
    connection.refresh_from_db()
    assert connection.status == "active"


def test_existing_registration_must_be_confirmed_by_meta(client, connection):
    connection.status = "setup_required"
    connection.save()
    url = f"/api/workspaces/{connection.workspace_id}/whatsapp/{connection.id}/activate/"
    with patch(
        "apps.channels.whatsapp.graph",
        side_effect=[{"data": [{"id": "222"}]}, {"status": "PENDING"}],
    ):
        result = client.post(url, {"already_registered": True}, format="json")
    assert result.status_code == 400
    connection.refresh_from_db()
    assert connection.status == "setup_required"


def test_templates_queue_outside_window_once_and_are_rechecked_before_delivery(
    client, conversation
):
    url = f"/api/workspaces/{conversation.workspace_id}/conversations/{conversation.id}/whatsapp-templates/"
    with patch("apps.channels.whatsapp_templates.graph", return_value={"data": [RAW]}) as graph:
        for _ in range(2):
            response = client.post(
                url, selection(), format="json", HTTP_IDEMPOTENCY_KEY="same-click"
            )
            assert response.status_code == 202, response.data
        assert graph.call_count == 1
    delivery = Delivery.objects.for_workspace(conversation.workspace_id).get()
    saved_message = Message.objects.for_workspace(conversation.workspace_id).get()
    assert saved_message.kind == "template" and "Alex" in saved_message.text
    with (
        patch("apps.channels.whatsapp_templates.graph", return_value={"data": [RAW]}),
        patch(
            "apps.channels.providers.request", return_value={"messages": [{"id": "wamid.1"}]}
        ) as send,
    ):
        send_now(delivery)
    delivery.refresh_from_db()
    assert delivery.status == "sent"
    payload = send.call_args.kwargs["json"]
    assert payload["type"] == "template" and payload["to"] == "15550101"
    assert payload["template"]["components"][0]["parameters"][0]["text"] == "Alex"
    assert payload["template"]["components"][1]["sub_type"] == "url"


@pytest.mark.parametrize("case", ["paused", "changed", "opted_out", "expired"])
def test_delayed_template_rechecks_policy_at_send_time(conversation, user, case):
    with patch("apps.channels.whatsapp_templates.graph", return_value={"data": [RAW]}):
        delivery = queue_reply(
            conversation, "", "template-check", actor=user, whatsapp_template=selection()
        )
    raw = copy.deepcopy(RAW)
    if case == "paused":
        raw["status"] = "PAUSED"
    if case == "changed":
        raw["components"][1]["text"] = "Different message"
    if case == "opted_out":
        lead = conversation.identity.lead
        lead.opted_out = True
        lead.save()
    if case == "expired":
        channel = conversation.identity.connection
        channel.expires_at = timezone.now() - timedelta(seconds=1)
        channel.save()
    with (
        patch("apps.channels.whatsapp_templates.graph", return_value={"data": [raw]}),
        patch("apps.channels.providers.request") as send,
    ):
        send_now(delivery)
    delivery.refresh_from_db()
    assert delivery.status == "failed"
    send.assert_not_called()


def test_invalid_fields_and_missing_consent_are_inline_errors(client, conversation):
    url = f"/api/workspaces/{conversation.workspace_id}/conversations/{conversation.id}/whatsapp-templates/"
    data = selection()
    data["consent_confirmed"] = False
    assert (
        "consent_confirmed" in client.post(url, data, format="json", HTTP_IDEMPOTENCY_KEY="1").data
    )
    data["consent_confirmed"] = True
    data["values"].pop("body_1")
    with patch("apps.channels.whatsapp_templates.graph", return_value={"data": [RAW]}):
        response = client.post(url, data, format="json", HTTP_IDEMPOTENCY_KEY="2")
    assert response.status_code == 400 and "body_1" in response.data
    assert not Delivery.objects.for_workspace(conversation.workspace_id).exists()


def test_plain_replies_remain_blocked_outside_window(conversation):
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError, match="window"):
        queue_reply(conversation, "Not a template", "ordinary")


@pytest.mark.parametrize(
    "phone_status,expected", [("CONNECTED", "active"), ("PENDING", "setup_required")]
)
def test_owned_account_can_connect_without_embedded_signup(
    client, workspace, settings, phone_status, expected
):
    settings.WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID = ""
    result = client.post(
        f"/api/workspaces/{workspace.id}/channels/connect/",
        {
            "provider": "whatsapp",
            "external_account_id": "222",
            "business_account_id": "333",
            "display_name": "My test number",
            "access_token": "own-test-token",
            "is_test": False,
        },
        format="json",
    )
    assert result.status_code == 202, result.data
    item = ChannelConnection.objects.for_workspace(workspace).get()
    with patch(
        "apps.channels.whatsapp.graph",
        side_effect=[{"data": [{"id": "222"}]}, {"status": phone_status}, {"success": True}],
    ):
        verify_connection(str(workspace.pk), str(item.pk))
    item.refresh_from_db()
    assert item.status == expected and item.profile["waba_id"] == "333"


def test_manual_owned_account_reconnect_keeps_thread_and_respects_capacity(
    client, workspace, connection, conversation
):
    set_limits(workspace, max_instagram_accounts=1)
    response = client.post(
        f"/api/workspaces/{workspace.pk}/channels/connect/",
        {
            "provider": "whatsapp",
            "external_account_id": "222",
            "business_account_id": "333",
            "display_name": "Reconnected",
            "access_token": "new-secret",
            "is_test": False,
        },
        format="json",
    )
    assert response.status_code == 202, response.data
    assert str(response.data["id"]) == str(connection.pk)
    assert ChannelConnection.objects.for_workspace(workspace).count() == 1
    assert Conversation.objects.for_workspace(workspace).filter(pk=conversation.pk).exists()


def test_manual_account_cannot_link_a_phone_from_another_business(connection):
    connection.status = "verifying"
    connection.save()
    with patch("apps.channels.whatsapp.graph", return_value={"data": [{"id": "444"}]}):
        verify_connection(str(connection.workspace_id), str(connection.pk))
    connection.refresh_from_db()
    assert connection.status == "reconnect_required"


def test_reconnecting_disconnected_number_rechecks_account_capacity(client, workspace, connection):
    set_limits(workspace, max_instagram_accounts=1)
    connection.status = "disconnected"
    connection.save()
    ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="telegram",
        external_account_id="other",
        display_name="Other",
        access_token="secret",
        expires_at=timezone.now() + timedelta(days=90),
    )
    response = client.post(
        f"/api/workspaces/{workspace.pk}/channels/connect/",
        {
            "provider": "whatsapp",
            "external_account_id": "222",
            "business_account_id": "333",
            "display_name": "Reconnected",
            "access_token": "new-secret",
            "is_test": False,
        },
        format="json",
    )
    assert response.status_code == 402


def test_template_access_is_tenant_scoped(client, conversation):
    stranger = User.objects.create_user(username="stranger", email="s@example.com")
    api = APIClient()
    api.force_authenticate(stranger)
    url = f"/api/workspaces/{conversation.workspace_id}/conversations/{conversation.id}/whatsapp-templates/"
    assert api.get(url).status_code in {403, 404}


def test_media_named_variables_and_unsupported_templates_are_explicit(connection):
    raw = {
        **RAW,
        "parameter_format": "NAMED",
        "components": [
            {"type": "HEADER", "format": "IMAGE"},
            {"type": "BODY", "text": "Hi {{first_name}}"},
        ],
    }
    chosen = {
        **selection(raw),
        "values": {"header_media": "https://cdn.example.com/image.jpg", "body_first_name": "Alex"},
    }
    with patch("apps.channels.whatsapp_templates.graph", return_value={"data": [raw]}):
        message, preview = prepare_template(connection, chosen)
    assert message["components"][0]["parameters"][0]["type"] == "image"
    assert message["components"][1]["parameters"][0]["parameter_name"] == "first_name"
    assert "Alex" in preview
    assert not template_definition({**RAW, "category": "AUTHENTICATION"})["supported"]
    assert not template_definition({**RAW, "components": [{"type": "CAROUSEL"}]})["supported"]


def test_template_ambiguous_send_is_not_automatically_retried(conversation, user):
    with patch("apps.channels.whatsapp_templates.graph", return_value={"data": [RAW]}):
        delivery = queue_reply(
            conversation, "", "ambiguous-template", actor=user, whatsapp_template=selection()
        )
        with patch("apps.channels.providers.request", side_effect=AmbiguousDelivery()) as send:
            send_now(delivery)
            send_delivery(str(conversation.workspace_id), str(delivery.id))
    assert send.call_count == 1
    delivery.refresh_from_db()
    assert delivery.status == "unknown"


def test_signed_whatsapp_receipts_dedupe_and_never_regress_or_create_inbound_messages(connection):
    item = Delivery.objects.for_workspace(connection.workspace_id).create(
        workspace_id=connection.workspace_id,
        connection=connection,
        recipient_id="15550101",
        idempotency_key="receipts",
        payload="{}",
        available_at=timezone.now(),
        status="sent",
        provider_message_id="wamid.1",
    )
    client = Client()
    for status in ["read", "delivered", "read", "sent"]:
        body = json.dumps(
            {
                "entry": [
                    {
                        "id": "333",
                        "changes": [
                            {
                                "field": "messages",
                                "value": {
                                    "metadata": {"phone_number_id": "222"},
                                    "statuses": [
                                        {
                                            "id": "wamid.1",
                                            "status": status,
                                            "timestamp": "1793000000",
                                            "recipient_id": "15550101",
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                ]
            }
        ).encode()
        signature = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
        assert (
            client.post("/webhooks/whatsapp/", body, content_type="application/json").status_code
            == 403
        )
        assert (
            client.post(
                "/webhooks/whatsapp/",
                body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
            ).status_code
            == 200
        )
        for event in WebhookEvent.objects.for_workspace(connection.workspace_id).filter(
            status="pending"
        ):
            process_webhook(str(connection.workspace_id), str(event.pk))
    item.refresh_from_db()
    assert item.provider_status == "read"
    assert WebhookEvent.objects.for_workspace(connection.workspace_id).count() == 3
    assert not Message.objects.for_workspace(connection.workspace_id).exists()
