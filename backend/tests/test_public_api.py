"""API keys, the /api/v1/ surface and signed outbound webhooks."""

import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
from apps.crm.services import receive
from apps.public_api.models import APIKey, OutboundWebhook, WebhookSubscription
from apps.public_api.services import emit
from apps.public_api.tasks import deliver_webhook, dispatch_outbound_webhooks
from apps.tenants.models import User
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def public_urls(request):
    if request.node.get_closest_marker("real_dns"):
        yield
        return
    with (
        patch("apps.public_api.views.is_public_https", return_value=True),
        patch("apps.public_api.tasks.is_public_https", return_value=True),
        patch("apps.crm.services.notify"),
    ):
        yield


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


def inbound(channel, text, sender="lead-1"):
    event = WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id=f"evt-{WebhookEvent.all_objects.count()}",
        payload="{}",
        available_at=timezone.now(),
    )
    return receive(event, {"sender_id": sender, "text": text})


def make_key(client, workspace, scopes=("read", "write")):
    response = client.post(
        f"/api/workspaces/{workspace.pk}/api-keys/",
        {"name": "Zapier", "scopes": list(scopes)},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def api(key):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=key)
    return client


def test_key_is_shown_once_and_stored_hashed(client, workspace):
    created = make_key(client, workspace)
    raw = created["key"]
    stored = APIKey.objects.for_workspace(workspace).get()
    assert raw.startswith("nmk_") and stored.key_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in json.dumps(client.get(f"/api/workspaces/{workspace.pk}/api-keys/").json())
    assert stored.prefix == raw[:12]


def test_key_auth_scopes_and_tenant_isolation(client, workspace, channel):
    message = inbound(channel, "hello")
    read_only = make_key(client, workspace, scopes=("read",))["key"]
    full = make_key(client, workspace)["key"]
    assert APIClient().get("/api/v1/leads/").status_code == 401
    assert api("nmk_wrong").get("/api/v1/leads/").status_code == 401
    listed = api(read_only).get("/api/v1/leads/")
    assert listed.status_code == 200 and len(listed.json()["results"]) == 1
    lead_id = listed.json()["results"][0]["id"]
    assert (
        api(read_only)
        .patch(f"/api/v1/leads/{lead_id}/", {"stage": "qualified"}, format="json")
        .status_code
        == 403
    )
    updated = api(full).patch(f"/api/v1/leads/{lead_id}/", {"stage": "qualified"}, format="json")
    assert updated.status_code == 200 and updated.json()["stage"] == "qualified"

    stranger = User.objects.create_user(username="s", email="s@example.com")
    other = create_workspace(stranger, "Other")
    theirs = APIClient()
    theirs.force_authenticate(stranger)
    their_key = make_key(theirs, other)["key"]
    assert api(their_key).get("/api/v1/leads/").json()["results"] == []
    assert api(their_key).get(f"/api/v1/leads/{lead_id}/").status_code == 404
    assert (
        api(their_key)
        .post(
            f"/api/v1/conversations/{message.conversation_id}/messages/",
            {"text": "x", "idempotency_key": "k"},
            format="json",
        )
        .status_code
        == 404
    )


def test_cursor_pagination_and_send_message(client, workspace, channel):
    for i in range(3):
        inbound(channel, f"m{i}", sender=f"lead-{i}")
    key = make_key(client, workspace)["key"]
    page = api(key).get("/api/v1/conversations/?limit=2").json()
    assert len(page["results"]) == 2 and page["next_cursor"]
    rest = api(key).get(f"/api/v1/conversations/?limit=2&cursor={page['next_cursor']}").json()
    assert len(rest["results"]) == 1 and rest["next_cursor"] is None
    conversation_id = page["results"][0]["id"]
    sent = api(key).post(
        f"/api/v1/conversations/{conversation_id}/messages/",
        {"text": "Thanks!", "idempotency_key": "abc"},
        format="json",
    )
    assert sent.status_code == 202
    api(key).post(
        f"/api/v1/conversations/{conversation_id}/messages/",
        {"text": "Thanks!", "idempotency_key": "abc"},
        format="json",
    )
    assert Delivery.objects.for_workspace(workspace).count() == 1
    messages = api(key).get(f"/api/v1/conversations/{conversation_id}/messages/").json()["results"]
    assert [m["direction"] for m in messages] == ["outbound", "inbound"]


def test_revoking_a_key_disables_it_and_its_subscriptions(client, workspace):
    created = make_key(client, workspace)
    key = created["key"]
    sub = api(key).post(
        "/api/v1/webhooks/",
        {"url": "https://hooks.zapier.com/x", "events": ["lead.created"]},
        format="json",
    )
    assert sub.status_code == 201 and sub.json()["secret"].startswith("whsec_")
    assert sub.json()["token"].startswith("whtok_")
    assert (
        client.delete(f"/api/workspaces/{workspace.pk}/api-keys/{created['id']}/").status_code
        == 204
    )
    assert api(key).get("/api/v1/leads/").status_code == 401
    assert not WebhookSubscription.objects.for_workspace(workspace).get().active


def test_events_are_emitted_only_to_matching_active_subscriptions(client, workspace, channel):
    WebhookSubscription.objects.for_workspace(workspace).create(
        workspace=workspace, url="https://a.example.com/", events=["lead.created"], secret="a"
    )
    WebhookSubscription.objects.for_workspace(workspace).create(
        workspace=workspace, url="https://b.example.com/", events=["message.received"], secret="b"
    )
    WebhookSubscription.objects.for_workspace(workspace).create(
        workspace=workspace,
        url="https://c.example.com/",
        events=["lead.created"],
        secret="c",
        active=False,
    )
    inbound(channel, "hello")
    events = sorted(
        OutboundWebhook.objects.for_workspace(workspace).values_list("event", flat=True)
    )
    assert events == ["lead.created", "message.received"]
    with pytest.raises(ValueError):
        emit(workspace.pk, "not.an.event", {})


def test_delivery_is_signed_and_backs_off_then_fails(workspace):
    sub = WebhookSubscription.objects.for_workspace(workspace).create(
        workspace=workspace,
        url="https://a.example.com/",
        events=["lead.hot"],
        secret="topsecret",
        token="whtok_shared",
    )
    emit(workspace.pk, "lead.hot", {"id": "1"})
    hook = OutboundWebhook.objects.for_workspace(workspace).get()
    with patch("apps.public_api.tasks.httpx.post") as post:
        post.return_value = MagicMock(status_code=200)
        deliver_webhook(str(workspace.pk), str(hook.id))
        body = post.call_args.kwargs["content"]
        assert post.call_args.kwargs["headers"]["X-Nemio-Token"] == "whtok_shared"
        header = post.call_args.kwargs["headers"]["X-Nemio-Signature"]
        timestamp, digest = (part.split("=")[1] for part in header.split(","))
        expected = hmac.new(
            b"topsecret", f"{timestamp}.".encode() + body, hashlib.sha256
        ).hexdigest()
        assert digest == expected
        assert json.loads(body)["event"] == "lead.hot"
    hook.refresh_from_db()
    assert hook.status == "delivered" and hook.response_code == 200

    emit(workspace.pk, "lead.hot", {"id": "2"})
    hook = OutboundWebhook.objects.for_workspace(workspace).filter(status="pending").get()
    with patch("apps.public_api.tasks.httpx.post", side_effect=httpx.ConnectError("x")):
        deliver_webhook(str(workspace.pk), str(hook.id))
    hook.refresh_from_db()
    assert (hook.status, hook.attempts) == ("pending", 1)
    assert hook.available_at > timezone.now() + timedelta(seconds=30)
    with patch("apps.public_api.tasks.httpx.post") as post:
        dispatch_outbound_webhooks()
        post.assert_not_called()  # not due yet
    hook.attempts = 7
    hook.available_at = timezone.now()
    hook.save()
    with patch("apps.public_api.tasks.httpx.post", return_value=MagicMock(status_code=500)):
        deliver_webhook(str(workspace.pk), str(hook.id))
    hook.refresh_from_db()
    sub.refresh_from_db()
    assert hook.status == "failed" and sub.failure_count == 2


@pytest.mark.real_dns
def test_private_targets_are_refused_without_mocks(client, workspace):
    from apps.public_api.tasks import is_public_https

    with patch(
        "apps.public_api.tasks.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("127.0.0.1", 443))],
    ):
        assert not is_public_https("https://internal.example.com/")
    assert not is_public_https("http://example.com/")


def test_key_management_requires_owner(workspace, user):
    from apps.tenants.models import Membership

    admin = User.objects.create_user(username="a", email="a@example.com")
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=admin, role="admin"
    )
    client = APIClient()
    client.force_authenticate(admin)
    assert (
        client.post(
            f"/api/workspaces/{workspace.pk}/api-keys/",
            {"name": "x", "scopes": ["read"]},
            format="json",
        ).status_code
        == 403
    )
    assert client.get(f"/api/workspaces/{workspace.pk}/api-keys/").status_code == 200
