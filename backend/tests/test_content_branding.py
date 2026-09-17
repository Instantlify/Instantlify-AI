"""Content calendar, link-in-bio, white-label branding/agency, Messenger and Sentry scrubbing."""

import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics.models import FunnelEvent
from apps.channels.models import ChannelConnection, WebhookEvent
from apps.content.models import BioPage, ScheduledPost
from apps.content.tasks import dispatch_scheduled_posts, publish_post
from apps.tenants.models import Membership, User, Workspace, WorkspaceBranding
from apps.tenants.observability import scrub
from apps.tenants.services import create_workspace

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


def as_user(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


# ---------------- content calendar ----------------


def test_schedule_publish_and_cancel_posts(client, workspace, channel):
    url = f"/api/workspaces/{workspace.pk}/posts/"
    when = (timezone.now() + timedelta(hours=2)).isoformat()
    bad = client.post(
        url,
        {"connection": channel.pk, "media_url": "http://insecure/x.jpg", "scheduled_at": when},
        format="json",
    )
    assert bad.status_code == 400
    past = client.post(
        url,
        {
            "connection": channel.pk,
            "media_url": "https://cdn.example.com/x.jpg",
            "scheduled_at": (timezone.now() - timedelta(minutes=1)).isoformat(),
        },
        format="json",
    )
    assert past.status_code == 400
    created = client.post(
        url,
        {
            "connection": channel.pk,
            "caption": "Launch day",
            "media_url": "https://cdn.example.com/x.jpg",
            "scheduled_at": when,
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    post = ScheduledPost.objects.for_workspace(workspace).get()
    with patch.object(publish_post, "delay") as delay:
        dispatch_scheduled_posts()
        delay.assert_not_called()  # not due
    ScheduledPost.objects.for_workspace(workspace).update(scheduled_at=timezone.now())
    publish_post(str(workspace.pk), str(post.id))
    publish_post(str(workspace.pk), str(post.id))
    post.refresh_from_db()
    assert post.status == "published" and post.provider_post_id.startswith("fake-post-")
    assert post.attempts == 1
    assert client.delete(f"{url}{post.pk}/").status_code == 400  # published: cannot cancel
    another = client.post(
        url,
        {
            "connection": channel.pk,
            "media_url": "https://cdn.example.com/y.jpg",
            "scheduled_at": when,
        },
        format="json",
    ).json()
    assert client.delete(f"{url}{another['id']}/").status_code == 204
    assert (
        ScheduledPost.objects.for_workspace(workspace).get(pk=another["id"]).status == "cancelled"
    )


def test_post_failures_back_off_and_then_fail(workspace, channel):
    from apps.channels.transport import ProviderError, RetryableError

    post = ScheduledPost.objects.for_workspace(workspace).create(
        workspace=workspace,
        connection=channel,
        media_url="https://cdn.example.com/x.jpg",
        scheduled_at=timezone.now(),
    )
    with patch("apps.content.tasks.adapter_for") as adapter:
        adapter.return_value.create_media_container.side_effect = RetryableError(120)
        publish_post(str(workspace.pk), str(post.id))
    post.refresh_from_db()
    assert post.status == "scheduled" and post.scheduled_at > timezone.now() + timedelta(
        seconds=100
    )
    post.scheduled_at = timezone.now()
    post.save()
    with patch("apps.content.tasks.adapter_for") as adapter:
        adapter.return_value.create_media_container.side_effect = ProviderError(
            "media_container_failed"
        )
        publish_post(str(workspace.pk), str(post.id))
    post.refresh_from_db()
    assert (post.status, post.error_code) == ("failed", "media_container_failed")


def test_posts_require_an_active_instagram_connection_in_workspace(client, workspace, channel):
    other_owner = User.objects.create_user(username="o", email="o@example.com")
    other = create_workspace(other_owner, "Other")
    foreign = ChannelConnection.objects.for_workspace(other).create(
        workspace=other,
        external_account_id="theirs",
        display_name="x",
        access_token="t",
        expires_at=timezone.now() + timedelta(days=1),
        is_test=True,
    )
    when = (timezone.now() + timedelta(hours=1)).isoformat()
    response = client.post(
        f"/api/workspaces/{workspace.pk}/posts/",
        {
            "connection": foreign.pk,
            "media_url": "https://cdn.example.com/x.jpg",
            "scheduled_at": when,
        },
        format="json",
    )
    assert response.status_code == 400


# ---------------- link in bio ----------------


def test_bio_page_public_view_and_click_tracking(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/bio/"
    assert client.get(url).json() == {}
    bad = client.put(url, {"slug": "API", "title": "x", "links": []}, format="json")
    assert bad.status_code == 400
    saved = client.put(
        url,
        {
            "slug": "Acme-Studio",
            "title": "Acme Studio",
            "bio": "Book a call",
            "links": [
                {"title": "Book", "url": "https://cal.com/acme"},
                {"title": "Bad", "url": "javascript:alert(1)"},
            ],
            "published": True,
        },
        format="json",
    )
    assert saved.status_code == 400  # javascript: link rejected
    saved = client.put(
        url,
        {
            "slug": "Acme-Studio",
            "title": "Acme Studio",
            "bio": "Book a call",
            "links": [{"title": "Book", "url": "https://cal.com/acme"}],
            "published": True,
        },
        format="json",
    )
    assert saved.status_code == 200, saved.content
    assert saved.json()["slug"] == "acme-studio"
    anonymous = APIClient()
    page = anonymous.get("/api/public/bio/ACME-STUDIO/").json()
    assert page["title"] == "Acme Studio" and page["links"][0]["index"] == 0
    assert "workspace" not in page and page["branding"]["brand_name"] == "Nemio"
    click = anonymous.post("/api/public/bio/acme-studio/", {"index": 0}, format="json")
    assert click.status_code == 200 and click.json()["url"] == "https://cal.com/acme"
    assert (
        anonymous.post("/api/public/bio/acme-studio/", {"index": 9}, format="json").status_code
        == 404
    )
    assert FunnelEvent.objects.for_workspace(workspace).filter(kind="link_click").count() == 1
    client.put(url, {"published": False}, format="json")
    assert anonymous.get("/api/public/bio/acme-studio/").status_code == 404


def test_bio_slugs_are_globally_unique(client, workspace):
    client.put(
        f"/api/workspaces/{workspace.pk}/bio/", {"slug": "taken", "title": "x"}, format="json"
    )
    other_owner = User.objects.create_user(username="o", email="o@example.com")
    other = create_workspace(other_owner, "Other")
    response = as_user(other_owner).put(
        f"/api/workspaces/{other.pk}/bio/", {"slug": "taken", "title": "y"}, format="json"
    )
    assert response.status_code == 400 and "slug" in response.json()
    assert BioPage.all_objects.count() == 1


# ---------------- branding / agency ----------------


def test_agency_creates_client_workspaces_that_inherit_branding(client, workspace, user):
    branding = client.put(
        f"/api/workspaces/{workspace.pk}/branding/",
        {
            "brand_name": "Growth Co",
            "primary_color": "#123ABC",
            "custom_domain": "App.GrowthCo.com",
        },
        format="json",
    )
    assert branding.status_code == 200, branding.content
    created = client.post(
        f"/api/workspaces/{workspace.pk}/clients/", {"name": "Client A"}, format="json"
    )
    assert created.status_code == 201, created.content
    client_ws = Workspace.objects.get(pk=created.json()["id"])
    assert client_ws.parent_id == workspace.pk
    assert Membership.objects.for_workspace(client_ws).get(user=user).role == "owner"
    effective = client.get(f"/api/workspaces/{client_ws.pk}/branding/").json()
    assert effective["own"] is None
    assert effective["effective"]["brand_name"] == "Growth Co"
    assert effective["effective"]["primary_color"] == "#123abc"
    assert effective["inherited_from"] == str(workspace.pk)
    listed = client.get(f"/api/workspaces/{workspace.pk}/clients/").json()
    assert [c["name"] for c in listed] == ["Client A"]
    # Clients cannot become agencies themselves.
    nested = client.post(
        f"/api/workspaces/{client_ws.pk}/clients/", {"name": "Nested"}, format="json"
    )
    assert nested.status_code == 400
    # Workspace list exposes the effective branding for the app shell.
    workspaces = client.get("/api/workspaces/").json()["results"]
    assert {w["branding"]["brand_name"] for w in workspaces} == {"Growth Co"}


def test_public_branding_resolves_by_host_and_domains_are_unique(client, workspace):
    client.put(
        f"/api/workspaces/{workspace.pk}/branding/",
        {
            "brand_name": "Growth Co",
            "custom_domain": "app.growthco.com",
            "hide_platform_branding": True,
        },
        format="json",
    )
    with override_settings(ALLOWED_HOSTS=["app.growthco.com", "testserver"]):
        resolved = APIClient().get("/api/public/branding/", HTTP_HOST="app.growthco.com").json()
    assert resolved["brand_name"] == "Growth Co" and resolved["hide_platform_branding"] is True
    default = APIClient().get("/api/public/branding/").json()
    assert default["brand_name"] == "Nemio"
    other_owner = User.objects.create_user(username="o", email="o@example.com")
    other = create_workspace(other_owner, "Other")
    clash = as_user(other_owner).put(
        f"/api/workspaces/{other.pk}/branding/",
        {"brand_name": "Copycat", "custom_domain": "app.growthco.com"},
        format="json",
    )
    assert clash.status_code == 400
    assert WorkspaceBranding.all_objects.count() == 1


def test_branding_is_owner_only(workspace):
    admin = User.objects.create_user(username="a", email="a@example.com")
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=admin, role="admin"
    )
    response = as_user(admin).put(
        f"/api/workspaces/{workspace.pk}/branding/", {"brand_name": "x"}, format="json"
    )
    assert response.status_code == 403
    assert as_user(admin).get(f"/api/workspaces/{workspace.pk}/branding/").status_code == 200


# ---------------- Messenger ----------------


@override_settings(META_APP_SECRET="ig-secret", MESSENGER_APP_SECRET="page-secret")
def test_messenger_webhook_uses_its_own_secret(workspace):
    connection = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="messenger",
        external_account_id="page-1",
        display_name="Page",
        access_token="t",
        expires_at=timezone.now() + timedelta(days=60),
    )
    body = json.dumps(
        {
            "object": "page",
            "entry": [
                {
                    "id": "page-1",
                    "messaging": [
                        {"sender": {"id": "psid-1"}, "message": {"mid": "m1", "text": "Hi"}}
                    ],
                }
            ],
        }
    ).encode()
    wrong = "sha256=" + hmac.new(b"ig-secret", body, hashlib.sha256).hexdigest()
    right = "sha256=" + hmac.new(b"page-secret", body, hashlib.sha256).hexdigest()
    http = Client()
    assert (
        http.post(
            "/webhooks/messenger/",
            body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=wrong,
        ).status_code
        == 403
    )
    assert (
        http.post(
            "/webhooks/messenger/",
            body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=right,
        ).status_code
        == 200
    )
    event = WebhookEvent.objects.for_workspace(workspace).get(connection=connection)
    assert json.loads(event.payload)["sender_id"] == "psid-1"


def test_messenger_send_and_window_rules(workspace):
    from apps.channels.providers import MessengerAdapter

    connection = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="messenger",
        external_account_id="page-1",
        display_name="Page",
        access_token="tok",
        expires_at=timezone.now() + timedelta(days=60),
    )
    with patch("apps.channels.providers.request", return_value={"message_id": "mid.1"}) as req:
        assert (
            MessengerAdapter(connection).send_message(
                recipient_id="psid", text="Hi", idempotency_key="k"
            )
            == "mid.1"
        )
        payload = req.call_args.kwargs["json"]
        assert payload["messaging_type"] == "RESPONSE" and payload["recipient"] == {"id": "psid"}
        assert "page-1/messages" in req.call_args.args[1]
    from apps.channels.adapters import WINDOWED_PROVIDERS

    assert "messenger" in WINDOWED_PROVIDERS


# ---------------- Sentry ----------------


def test_sentry_events_are_scrubbed_of_credentials_and_customer_data():
    event = {
        "request": {
            "url": "https://api.example.com/api/meta/callback/?code=SECRETCODE",
            "data": {"password": "x"},
            "cookies": {"sessionid": "s"},
            "query_string": "code=SECRETCODE",
            "headers": {"Authorization": "Bearer t", "X-API-Key": "nmk_1", "Accept": "*/*"},
        },
        "user": {"email": "owner@example.com"},
        "exception": {"values": [{"stacktrace": {"frames": [{"vars": {"token": "t"}}]}}]},
    }
    cleaned = scrub(event, {})
    request = cleaned["request"]
    assert "SECRETCODE" not in json.dumps(cleaned)
    assert "data" not in request and "cookies" not in request and "query_string" not in request
    assert request["headers"]["Authorization"] == "[filtered]"
    assert request["headers"]["X-API-Key"] == "[filtered]"
    assert request["headers"]["Accept"] == "*/*"
    assert "user" not in cleaned
    assert "vars" not in cleaned["exception"]["values"][0]["stacktrace"]["frames"][0]


# ---------------- integrations ----------------


def test_resaving_integration_options_keeps_stored_credentials(client, workspace):
    from apps.crm.models import IntegrationConfig

    url = f"/api/workspaces/{workspace.pk}/integrations/"
    first = client.post(
        url,
        {
            "provider": "slack",
            "credentials": {"api_key": "xoxb-1"},
            "options": {"channel_id": "C1"},
        },
        format="json",
    )
    assert first.status_code == 201, first.content
    again = client.post(
        url,
        {"provider": "slack", "credentials": {}, "options": {"channel_id": "C2"}},
        format="json",
    )
    assert again.status_code == 201
    item = IntegrationConfig.objects.for_workspace(workspace).get(provider="slack")
    assert json.loads(item.credentials) == {"api_key": "xoxb-1"}
    assert item.options == {"channel_id": "C2"}
    missing = client.post(
        url, {"provider": "notion", "options": {"database_id": "d"}}, format="json"
    )
    assert missing.status_code == 400
    assert "xoxb-1" not in client.get(url).content.decode()
