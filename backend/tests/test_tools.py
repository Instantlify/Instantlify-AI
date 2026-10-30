"""Deep links, the comment shield and the website chat widget."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.automations.models import ConversationState
from apps.channels.adapters import FakeChannelAdapter
from apps.channels.models import ChannelConnection, WebhookEvent
from apps.crm.models import Conversation, Message
from apps.crm.services import queue_reply, receive
from apps.tools.models import DeepLink, ShieldEvent

pytestmark = pytest.mark.django_db


def connect(workspace, provider="instagram"):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider=provider,
        external_account_id=f"{provider}-account",
        display_name=f"{provider} account",
        access_token="secret",
        expires_at=timezone.now() + timedelta(days=60),
        is_test=True,
    )


def inbound(channel, text, kind="dm", sender="lead-1", **extra):
    event = WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id=f"evt-{WebhookEvent.all_objects.count()}",
        payload="{}",
        available_at=timezone.now(),
    )
    return receive(event, {"sender_id": sender, "text": text, "kind": kind, **extra})


# Deep links


def test_deep_links_are_created_counted_and_paused(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/deeplinks/"
    created = client.post(
        url,
        {
            "title": "Profile",
            "platform": "instagram",
            "target": "https://instagram.com/x",
            "code": "IG-Profile",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    assert created.json()["code"] == "ig-profile"
    assert (
        client.post(
            url,
            {"title": "Dup", "platform": "custom", "target": "https://x.y", "code": "ig-profile"},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            url,
            {"title": "Bad", "platform": "custom", "target": "http://x.y", "code": "plain"},
            format="json",
        ).status_code
        == 400
    )

    anon = APIClient()
    hop = anon.get("/go/ig-profile/")
    assert hop.status_code == 302 and hop["Location"] == "https://instagram.com/x"
    assert client.get(url).json()[0]["clicks"] == 1

    link_id = created.json()["id"]
    assert client.patch(f"{url}{link_id}/", {"active": False}, format="json").status_code == 200
    unavailable = anon.get("/go/ig-profile/")
    assert unavailable.status_code == 404
    assert unavailable["Content-Type"].startswith("text/html")
    assert b"This link is unavailable" in unavailable.content
    assert unavailable["Cache-Control"] == "no-store"
    assert client.get(url).json()[0]["clicks"] == 1
    assert b"This link is unavailable" in anon.get("/go/unknown-link/").content
    assert client.delete(f"{url}{link_id}/").status_code == 204
    assert not DeepLink.all_objects.exists()


# Comment shield


def test_shield_hides_matching_comments_and_keeps_them_out_of_flows(client, workspace, settings):
    settings.CHANNEL_ADAPTER_MODE = "fake"
    rules = f"/api/workspaces/{workspace.pk}/shield/rules/"
    created = client.post(
        rules,
        {"name": "Spam", "keywords": [" DM me ", "crypto", "dm me"], "action": "hide"},
        format="json",
    )
    assert created.status_code == 201, created.content
    assert created.json()["keywords"] == ["dm me", "crypto"]
    assert (
        client.post(
            rules, {"name": "x", "keywords": [], "action": "hide"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            rules, {"name": "x", "keywords": ["a"], "action": "nuke"}, format="json"
        ).status_code
        == 400
    )

    channel = connect(workspace)
    adapter = FakeChannelAdapter()
    with patch("apps.channels.adapters.adapter_for", return_value=adapter):
        inbound(channel, "DM ME on telegram for crypto gains", kind="comment", comment_id="c-1")
        inbound(channel, "Lovely post!", kind="comment", comment_id="c-2")
    assert adapter.moderated == [("hide", "c-1")]
    events = client.get(f"/api/workspaces/{workspace.pk}/shield/events/").json()
    assert [
        (e["rule_name"], e["comment_id"], e["action_taken"], e["provider"]) for e in events
    ] == [("Spam", "c-1", "hidden", "instagram")]
    # The comment is still in the inbox, but it started no automation.
    assert Message.objects.for_workspace(workspace).filter(kind="comment").count() == 2
    assert not ConversationState.objects.for_workspace(workspace).exists()

    # A flag-only rule records the event and lets routing continue.
    rule_id = created.json()["id"]
    assert client.patch(f"{rules}{rule_id}/", {"action": "flag"}, format="json").status_code == 200
    with patch("apps.channels.adapters.adapter_for", return_value=adapter):
        inbound(channel, "crypto again", kind="comment", comment_id="c-3", sender="lead-2")
    assert adapter.moderated == [("hide", "c-1")]
    assert (
        ShieldEvent.objects.for_workspace(workspace).get(comment_id="c-3").action_taken == "flagged"
    )

    # Disabled rules match nothing.
    client.patch(f"{rules}{rule_id}/", {"enabled": False}, format="json")
    inbound(channel, "crypto once more", kind="comment", comment_id="c-4", sender="lead-3")
    assert ShieldEvent.objects.for_workspace(workspace).count() == 2


# Website chat


def test_webchat_settings_and_public_widget_conversation(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/webchat/"
    assert client.get(url).json()["title"] == "Chat with us"
    saved = client.put(
        url,
        {
            "title": "Support",
            "greeting": "Hello!",
            "color": "#112233",
            "bot_enabled": False,
            "allowed_domains": ["https://Shop.Example.com/page", "example.org"],
        },
        format="json",
    )
    assert saved.status_code == 200, saved.content
    assert saved.json()["allowed_domains"] == ["shop.example.com", "example.org"]
    assert client.put(url, {"color": "blue"}, format="json").status_code == 400

    public = f"/api/public/webchat/{workspace.pk}/"
    anon = APIClient()
    # Only the allowed sites may embed the widget.
    assert anon.get(public, HTTP_ORIGIN="https://evil.example.net").status_code == 400
    config = anon.get(public, HTTP_ORIGIN="https://www.shop.example.com")
    assert config.status_code == 200
    assert (config.json()["title"], config.json()["color"]) == ("Support", "#112233")

    visitor = "visitor-abc12345"
    sent = anon.post(
        public,
        {"visitor": visitor, "text": "Is this in stock?"},
        format="json",
        HTTP_ORIGIN="https://example.org",
    )
    assert sent.status_code == 201, sent.content
    assert (
        anon.post(
            public, {"visitor": "x", "text": "hi"}, format="json", HTTP_ORIGIN="https://example.org"
        ).status_code
        == 400
    )

    conversation = Conversation.objects.for_workspace(workspace).get()
    assert conversation.identity.connection.provider == "webchat"
    assert conversation.identity.external_id == visitor
    # The same visitor keeps one conversation and one channel.
    anon.post(
        public,
        {"visitor": visitor, "text": "Hello?"},
        format="json",
        HTTP_ORIGIN="https://example.org",
    )
    assert Conversation.objects.for_workspace(workspace).count() == 1
    assert (
        ChannelConnection.objects.for_workspace(workspace).filter(provider="webchat").count() == 1
    )

    queue_reply(conversation, "Yes, three left.", "reply-1")
    thread = anon.get(public, {"visitor": visitor}, HTTP_ORIGIN="https://example.org").json()[
        "messages"
    ]
    assert [(m["direction"], m["text"]) for m in thread] == [
        ("inbound", "Is this in stock?"),
        ("inbound", "Hello?"),
        ("outbound", "Yes, three left."),
    ]
    # Another visitor never sees that thread.
    assert (
        anon.get(public, {"visitor": "someone-else-1"}, HTTP_ORIGIN="https://example.org").json()[
            "messages"
        ]
        == []
    )
