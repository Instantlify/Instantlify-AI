"""Meta client surfaces: app dock pins, account switcher data, channel-scoped triggers,
Facebook Page comments, automation management, the AI flow generator, the dual-bubble
inbox, the CRM pipeline and overview telemetry."""

import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.agents.models import AgentConfig
from apps.analytics.models import Experiment
from apps.automations.generator import graph_from_completion
from apps.automations.models import Automation, ConversationState, Trigger
from apps.automations.tasks import step
from apps.channels.ingress import normalize_meta
from apps.channels.models import ChannelConnection, WebhookEvent
from apps.crm.models import Conversation, Lead
from apps.crm.services import receive
from apps.tenants.models import Membership, User
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db

FLOW = {
    "start": "hello",
    "triggers": [{"kind": "comment", "keyword": "send"}],
    "nodes": [
        {"id": "hello", "data": {"kind": "send_message", "text": "Here you go"}},
        {"id": "done", "data": {"kind": "end"}},
    ],
    "edges": [{"source": "hello", "target": "done"}],
}


@pytest.fixture(autouse=True)
def quiet_notify():
    with patch("apps.crm.services.notify"):
        yield


def connect(workspace, provider="instagram", account="ig-account", **extra):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider=provider,
        external_account_id=account,
        display_name=f"{provider} account",
        access_token="secret",
        expires_at=timezone.now() + timedelta(days=60),
        is_test=True,
        **extra,
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


def agent_client(workspace):
    agent = User.objects.create_user(
        username="agent", email="agent@example.com", password="A-very-long-password42"
    )
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=agent, role="agent"
    )
    client = APIClient()
    client.force_authenticate(agent)
    return client


def published(client, workspace, flow=FLOW, name="Flow"):
    created = client.post(
        f"/api/workspaces/{workspace.pk}/automations/",
        {"name": name, "draft": flow},
        format="json",
    )
    assert created.status_code == 201, created.content
    item = client.post(
        f"/api/workspaces/{workspace.pk}/automations/{created.json()['id']}/publish/",
        {"graph": flow},
        format="json",
    )
    assert item.status_code == 200, item.content
    return Automation.objects.for_workspace(workspace).get(pk=created.json()["id"])


def run_flows(workspace):
    for state in ConversationState.objects.for_workspace(workspace).filter(status="running"):
        while True:
            step(str(workspace.pk), str(state.pk))
            state.refresh_from_db()
            if state.status != "running":
                break


# App dock


def test_pinned_apps_default_and_validation(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/"
    assert client.get(url).json()["pinned_apps"] == ["bio", "calendar"]
    assert client.patch(url, {"pinned_apps": ["calendar"]}, format="json").json()[
        "pinned_apps"
    ] == ["calendar"]
    for bad in (["calendar", "calendar"], ["unknown_app"], "bio"):
        assert client.patch(url, {"pinned_apps": bad}, format="json").status_code == 400
    assert agent_client(workspace).patch(url, {"pinned_apps": []}, format="json").status_code == 403


# Account switcher


def test_connections_expose_followers_and_refresh_tokens(client, workspace):
    channel = connect(workspace, profile={"followers_count": 1200, "biography": "private"})
    connect(workspace, "whatsapp", "15550001", profile={"followers_count": "many"})
    rows = {
        row["provider"]: row
        for row in client.get(f"/api/workspaces/{workspace.pk}/connections/").json()["results"]
    }
    assert rows["instagram"]["followers"] == 1200
    assert rows["whatsapp"]["followers"] is None
    assert "profile" not in rows["instagram"]
    response = client.post(f"/api/workspaces/{workspace.pk}/connections/refresh/")
    assert response.status_code == 202 and response.json() == {"queued": 1}
    channel.refresh_from_db()
    assert channel.last_refreshed_at is not None and channel.access_token == "fake-token"
    assert (
        agent_client(workspace)
        .post(f"/api/workspaces/{workspace.pk}/connections/refresh/")
        .status_code
        == 403
    )


# Channel-scoped triggers and Facebook Page comments


def test_trigger_channel_is_validated_and_scopes_matching(client, workspace):
    bad = {**FLOW, "triggers": [{"kind": "comment", "keyword": "send", "channel": "whatsapp"}]}
    item = client.post(
        f"/api/workspaces/{workspace.pk}/automations/",
        {"name": "Bad", "draft": bad},
        format="json",
    ).json()
    response = client.post(
        f"/api/workspaces/{workspace.pk}/automations/{item['id']}/publish/",
        {"graph": bad},
        format="json",
    )
    assert response.status_code == 400
    flow = {**FLOW, "triggers": [{"kind": "comment", "keyword": "send", "channel": "messenger"}]}
    automation = published(client, workspace, flow)
    assert (
        Trigger.objects.for_workspace(workspace).get(automation=automation).channel == "messenger"
    )
    instagram = connect(workspace)
    page = connect(workspace, "messenger", "page-1")
    inbound(instagram, "send please", kind="comment", comment_id="c-1")
    assert not ConversationState.objects.for_workspace(workspace).exists()
    inbound(page, "send please", kind="comment", sender="fb-user", comment_id="c-2")
    state = ConversationState.objects.for_workspace(workspace).get()
    assert state.conversation.identity.connection == page


def test_facebook_page_feed_comments_are_normalized():
    payload = {
        "entry": [
            {
                "id": "page-1",
                "changes": [
                    {
                        "field": "feed",
                        "value": {
                            "item": "comment",
                            "verb": "add",
                            "comment_id": "post_1_c9",
                            "message": "SEND",
                            "from": {"id": "fb-user"},
                        },
                    },
                    {
                        "field": "feed",
                        "value": {
                            "item": "comment",
                            "verb": "add",
                            "comment_id": "post_1_c10",
                            "message": "Thanks!",
                            "from": {"id": "page-1"},
                        },
                    },
                    {
                        "field": "feed",
                        "value": {"item": "reaction", "verb": "add", "from": {"id": "x"}},
                    },
                ],
            }
        ]
    }
    events = list(normalize_meta(payload, "messenger"))
    assert events == [
        (
            "page-1",
            "comment:post_1_c9",
            {
                "sender_id": "fb-user",
                "sender_name": "",
                "text": "SEND",
                "kind": "comment",
                "comment_id": "post_1_c9",
                "attachments": [],
            },
        )
    ]


def test_messenger_private_reply_addresses_the_comment(workspace):
    from apps.channels.providers import MessengerAdapter

    channel = connect(workspace, "messenger", "page-1")
    with patch("apps.channels.providers.request", return_value={"message_id": "m1"}) as sent:
        MessengerAdapter(channel).send_message(
            recipient_id="post_1_c9", text="Hi", idempotency_key="k", private_reply=True
        )
        MessengerAdapter(channel).send_message(recipient_id="psid", text="Hi", idempotency_key="j")
    assert sent.call_args_list[0].kwargs["json"]["recipient"] == {"comment_id": "post_1_c9"}
    assert sent.call_args_list[1].kwargs["json"]["recipient"] == {"id": "psid"}


# Automation management


def test_folder_duplicate_delete_and_stats(client, workspace):
    prefix = f"/api/workspaces/{workspace.pk}/automations"
    automation = published(client, workspace)
    response = client.patch(
        f"{prefix}/{automation.pk}/", {"folder": "  Comment leads "}, format="json"
    )
    assert response.json()["folder"] == "Comment leads"
    copy = client.post(f"{prefix}/{automation.pk}/duplicate/").json()
    assert copy["name"] == "Flow (copy)" and copy["folder"] == "Comment leads"
    assert copy["enabled"] is False and copy["draft"]["start"] == "hello"

    channel = connect(workspace)
    inbound(channel, "send", kind="comment", comment_id="c-1")
    inbound(channel, "send", kind="comment", sender="lead-2", comment_id="c-2")
    stats = client.get(f"{prefix}/stats/").json()
    assert stats == {str(automation.pk): {"runs": 2, "reach": 2}}

    Experiment.objects.for_workspace(workspace).create(
        workspace=workspace,
        name="Test",
        control=automation,
        variant=Automation.objects.for_workspace(workspace).get(pk=copy["id"]),
    )
    assert client.delete(f"{prefix}/{automation.pk}/").status_code == 400
    Experiment.objects.for_workspace(workspace).all().delete()
    assert client.delete(f"{prefix}/{automation.pk}/").status_code == 204
    assert not Automation.objects.for_workspace(workspace).filter(pk=automation.pk).exists()
    assert agent_client(workspace).delete(f"{prefix}/{copy['id']}/").status_code == 403


def test_transfer_requires_a_managed_destination_and_reason(client, user, workspace):
    prefix = f"/api/workspaces/{workspace.pk}/automations"
    automation = published(client, workspace)
    other = create_workspace(user, "Second")
    stranger = create_workspace(
        User.objects.create_user(username="s", email="s@example.com", password="x" * 20), "Theirs"
    )
    url = f"{prefix}/{automation.pk}/transfer/"
    assert client.post(url, {"workspace": "nope", "reason": "x"}, format="json").status_code == 400
    assert (
        client.post(url, {"workspace": str(stranger.pk), "reason": "x"}, format="json").status_code
        == 404
    )
    assert client.post(url, {"workspace": str(other.pk)}, format="json").status_code == 400
    experiment = Experiment.objects.for_workspace(workspace).create(
        workspace=workspace,
        name="Arms",
        control=automation,
        variant=published(client, workspace, name="Variant"),
    )
    blocked = client.post(url, {"workspace": str(other.pk), "reason": "x"}, format="json")
    assert blocked.status_code == 400 and "experiment" in blocked.content.decode()
    experiment.delete()
    response = client.post(
        url, {"workspace": str(other.pk), "reason": "Client handover"}, format="json"
    )
    assert response.status_code == 200
    moved = Automation.all_objects.get(pk=automation.pk)
    assert moved.workspace_id == other.pk and moved.enabled is False


# AI flow generator


def test_generate_creates_a_valid_disabled_draft(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/automations/generate/"
    assert client.post(url, {"prompt": "Comment to DM"}, format="json").status_code == 400
    AgentConfig.objects.for_workspace(workspace).create(workspace=workspace, is_test=True)
    response = client.post(
        url,
        {"prompt": "Create an Instagram comment-to-DM workflow that asks for an email"},
        format="json",
    )
    assert response.status_code == 201, response.content
    item = response.json()
    assert item["enabled"] is False and item["published"] == {}
    assert item["draft"]["triggers"] == [
        {"kind": "comment", "keyword": "SEND", "channel": "instagram"}
    ]
    assert all("position" in node for node in item["draft"]["nodes"])
    assert client.post(url, {"prompt": ""}, format="json").status_code == 400


def test_generated_graph_is_sanitized_and_validated():
    name, graph = graph_from_completion(
        "Sure! ```json\n"
        + json.dumps(
            {
                "name": "x" * 200,
                "start": "a",
                "triggers": [{"kind": "dm", "keyword": "hi", "evil": 1}],
                "nodes": [
                    {"id": "a", "data": {"kind": "send_message", "text": "Hi", "script": "x"}},
                    {"id": "b", "data": {"kind": "end"}},
                ],
                "edges": [{"source": "a", "target": "b", "sourceHandle": "weird"}],
            }
        )
        + "\n```"
    )
    assert len(name) == 100
    assert graph["triggers"] == [{"kind": "dm", "keyword": "hi", "channel": ""}]
    assert graph["nodes"][0]["data"] == {"kind": "send_message", "text": "Hi"}
    assert "sourceHandle" not in graph["edges"][0]
    for bad in (
        "no json here",
        "{not json}",
        json.dumps({"start": "a", "nodes": [], "edges": [], "triggers": []}),
        json.dumps(
            {
                "start": "a",
                "triggers": [{"kind": "dm", "keyword": "hi"}],
                "nodes": [{"id": "a", "data": {"kind": "delay", "seconds": "soon"}}],
                "edges": [],
            }
        ),
    ):
        with pytest.raises(ValidationError):
            graph_from_completion(bad)


# Inbox


def test_messages_report_their_sender_and_threads_their_events(client, user, workspace):
    automation = published(client, workspace)
    channel = connect(workspace)
    inbound(channel, "send", kind="comment", comment_id="c-1")
    run_flows(workspace)
    conversation = Conversation.objects.for_workspace(workspace).get()
    prefix = f"/api/workspaces/{workspace.pk}/conversations/{conversation.pk}"
    blocked = client.post(
        f"{prefix}/messages/", {"text": "Too early"}, format="json", HTTP_IDEMPOTENCY_KEY="early"
    )
    assert blocked.status_code == 400
    inbound(channel, "Yes, please", kind="dm")
    sent = client.post(
        f"{prefix}/messages/", {"text": "Human here"}, format="json", HTTP_IDEMPOTENCY_KEY="k1"
    )
    assert sent.status_code == 202, sent.content
    rows = client.get(f"{prefix}/messages/").json()["results"][::-1]
    assert [(row["sender"], row["author_name"]) for row in rows] == [
        ("customer", ""),
        ("automation", ""),
        ("customer", ""),
        ("human", user.email),
    ]
    events = client.get(f"{prefix}/events/").json()
    assert [(event["kind"], event["automation_name"]) for event in events] == [
        ("triggered", automation.name)
    ]


def test_conversation_list_has_previews_and_channel_filters(client, workspace):
    instagram = connect(workspace)
    whatsapp = connect(workspace, "whatsapp", "15550001")
    inbound(instagram, "hello from instagram")
    inbound(whatsapp, "hi from whatsapp", sender="+1 (555) 010-0200")
    url = f"/api/workspaces/{workspace.pk}/conversations/"
    rows = {row["provider"]: row for row in client.get(url).json()["results"]}
    assert rows["instagram"]["last_message"]["text"] == "hello from instagram"
    assert rows["instagram"]["contact_link"] == ""
    assert rows["whatsapp"]["contact_link"] == "https://wa.me/15550100200"
    assert rows["whatsapp"]["connection_id"] == str(whatsapp.pk)
    assert [
        row["provider"] for row in client.get(url + "?provider=whatsapp").json()["results"]
    ] == ["whatsapp"]
    assert [
        row["provider"] for row in client.get(url + f"?connection={instagram.pk}").json()["results"]
    ] == ["instagram"]
    assert client.get(url + "?connection=bad").status_code == 400


# CRM


def test_lead_rows_filters_bulk_actions_and_broadcast(client, workspace):
    instagram = connect(workspace)
    whatsapp = connect(workspace, "whatsapp", "15550001")
    first = inbound(instagram, "hi", sender="ig-1").conversation.identity.lead
    second = inbound(whatsapp, "hello", sender="wa-1").conversation.identity.lead
    inbound(whatsapp, "again", sender="wa-1")
    url = f"/api/workspaces/{workspace.pk}/leads/"
    rows = {row["id"]: row for row in client.get(url + "?page_size=200").json()["results"]}
    assert rows[str(second.pk)]["channels"] == ["whatsapp"]
    assert rows[str(second.pk)]["message_count"] == 2
    assert rows[str(first.pk)]["conversation_id"] is not None
    assert [row["id"] for row in client.get(url + "?provider=instagram").json()["results"]] == [
        str(first.pk)
    ]

    bulk = f"{url}bulk/"
    ids = [str(first.pk), str(second.pk)]
    assert client.post(
        bulk, {"ids": ids, "action": "tag", "value": " vip "}, format="json"
    ).json() == {"updated": 2}
    staged = client.post(bulk, {"ids": ids, "action": "stage", "value": "booked"}, format="json")
    assert staged.status_code == 200
    assert (
        client.post(
            bulk, {"ids": ids, "action": "stage", "value": "nope"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(bulk, {"ids": ["x"], "action": "tag", "value": "a"}, format="json").status_code
        == 400
    )
    assert client.post(bulk, {"ids": ids, "action": "drop"}, format="json").status_code == 400
    first.refresh_from_db()
    assert first.tags == ["vip"] and first.stage == "booked"
    client.post(bulk, {"ids": ids, "action": "untag", "value": "vip"}, format="json")
    first.refresh_from_db()
    assert first.tags == []
    assert [row["id"] for row in client.get(url + "?stage=booked").json()["results"]]

    Conversation.objects.for_workspace(workspace).filter(identity__lead=first).update(
        last_inbound_at=timezone.now() - timedelta(days=2)
    )
    broadcast = f"{url}broadcast/"
    assert client.post(broadcast, {"ids": ids, "text": "News"}, format="json").status_code == 400
    response = client.post(
        broadcast, {"ids": ids, "text": "News"}, format="json", HTTP_IDEMPOTENCY_KEY="b1"
    )
    assert response.json() == {"queued": 1, "skipped": 1}
    again = client.post(
        broadcast, {"ids": ids, "text": "News"}, format="json", HTTP_IDEMPOTENCY_KEY="b1"
    )
    assert again.json() == {"queued": 1, "skipped": 1}
    assert (
        agent_client(workspace)
        .post(broadcast, {"ids": ids, "text": "x"}, format="json", HTTP_IDEMPOTENCY_KEY="b2")
        .status_code
        == 403
    )
    assert Lead.objects.for_workspace(workspace).count() == 2


def test_contact_added_by_hand_has_no_channel_or_messages(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/leads/"
    created = client.post(
        url,
        {"name": "Maya Chen", "email": "maya@example.com", "stage": "new", "provider": "instagram"},
        format="json",
    )
    assert created.status_code == 201, created.content
    row = created.json()
    assert (row["name"], row["channels"], row["message_count"]) == ("Maya Chen", [], 0)
    assert row["conversation_id"] is None
    assert not ChannelConnection.objects.for_workspace(workspace).exists()
    assert not Conversation.objects.for_workspace(workspace).exists()
    assert client.post(url, {"name": "X", "stage": "nope"}, format="json").status_code == 400


# Overview telemetry


def test_telemetry_counts_channels_contacts_and_ai_share(client, workspace):
    published(client, workspace)
    instagram = connect(workspace)
    whatsapp = connect(workspace, "whatsapp", "15550001")
    inbound(instagram, "send", kind="comment", comment_id="c-1")
    run_flows(workspace)
    message = inbound(whatsapp, "hello", sender="wa-1")
    from apps.crm.services import queue_reply

    queue_reply(message.conversation, "AI answer", "agent-reply:test")
    data = client.get(f"/api/workspaces/{workspace.pk}/telemetry/").json()
    assert len(data["days"]) == 14
    today = data["days"][-1]
    assert today["instagram"] == 1 and today["whatsapp"] == 1 and today["contacts"] == 2
    assert data["totals"] == {"inbound": 2, "contacts": 2, "conversations": 2, "ai_rate": 0.5}
    channels = {row["provider"]: row for row in data["channels"]}
    assert channels["instagram"]["top_automation"] == {"name": "Flow", "runs": 1}
    assert channels["whatsapp"]["median_response_minutes"] is not None
    assert (
        agent_client(workspace).get(f"/api/workspaces/{workspace.pk}/telemetry/").status_code == 403
    )
