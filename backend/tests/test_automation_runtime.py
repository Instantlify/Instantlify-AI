"""The live flow executor: automations.services.route_message + automations.tasks.step."""

import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.automations.models import ConversationState
from apps.automations.tasks import step
from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
from apps.crm.services import receive

pytestmark = pytest.mark.django_db

BUTTON = {"type": "web_url", "url": "https://example.com/pricing", "title": "Pricing"}


def graph(**overrides):
    value = {
        "start": "offer",
        "triggers": [{"kind": "comment", "keyword": "price"}],
        "nodes": [
            {
                "id": "offer",
                "data": {"kind": "send_buttons", "text": "Here you go", "buttons": [BUTTON]},
            },
            {"id": "ask", "data": {"kind": "wait", "variable": "answer"}},
            {"id": "check", "data": {"kind": "condition", "variable": "answer", "equals": "yes"}},
            {"id": "yes", "data": {"kind": "send_message", "text": "Great, {{answer}}!"}},
            {"id": "no", "data": {"kind": "send_message", "text": "No worries."}},
            {"id": "done", "data": {"kind": "end"}},
        ],
        "edges": [
            {"source": "offer", "target": "ask"},
            {"source": "ask", "target": "check"},
            {"source": "check", "target": "yes", "sourceHandle": "true"},
            {"source": "check", "target": "no", "sourceHandle": "false"},
            {"source": "yes", "target": "done"},
            {"source": "no", "target": "done"},
        ],
    }
    value.update(overrides)
    return value


@pytest.fixture(autouse=True)
def quiet_notify():
    with patch("apps.crm.services.notify"):
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


def publish(client, workspace, flow):
    created = client.post(
        f"/api/workspaces/{workspace.pk}/automations/",
        {"name": "Pricing", "draft": flow},
        format="json",
    )
    assert created.status_code == 201, created.content
    return client.post(
        f"/api/workspaces/{workspace.pk}/automations/{created.json()['id']}/publish/",
        {"graph": flow},
        format="json",
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


def run(state, limit=20):
    for _ in range(limit):
        state.refresh_from_db()
        if state.status != "running" or state.available_at > timezone.now():
            return state
        step(str(state.workspace_id), str(state.id))
    raise AssertionError("flow did not settle")


def deliveries(channel):
    return list(Delivery.objects.for_workspace(channel.workspace_id).order_by("created_at", "id"))


def test_comment_flow_private_reply_wait_resume_and_branch(client, workspace, channel):
    assert publish(client, workspace, graph()).status_code == 200
    message = inbound(channel, "What is the PRICE?", kind="comment", comment_id="c-1")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    assert (state.status, state.node_id) == ("waiting", "ask")
    [first] = deliveries(channel)
    payload = json.loads(first.payload)
    # The first reply to a comment is a private reply addressed to the comment itself.
    assert first.recipient_id == "c-1"
    assert payload["private_reply"] is True
    assert payload["buttons"] == [BUTTON]

    inbound(channel, "YES")
    state = run(state)
    assert state.status == "completed"
    assert state.variables["answer"] == "YES"
    second = deliveries(channel)[1]
    assert second.recipient_id == "lead-1"
    assert json.loads(second.payload)["text"] == "Great, YES!"
    assert state.conversation_id == message.conversation_id


def test_false_branch(client, workspace, channel):
    publish(client, workspace, graph())
    inbound(channel, "price", kind="comment", comment_id="c-2")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    inbound(channel, "maybe later")
    run(state)
    assert json.loads(deliveries(channel)[-1].payload)["text"] == "No worries."


@pytest.mark.parametrize(
    "text,kind",
    [("priceless", "comment"), ("price", "dm"), ("the pricing page", "comment")],
)
def test_trigger_requires_kind_and_whole_word(client, workspace, channel, text, kind):
    publish(client, workspace, graph())
    inbound(channel, text, kind=kind, comment_id="c-3")
    assert not ConversationState.objects.for_workspace(workspace).exists()


def test_cooldown_blocks_retrigger_after_completion(client, workspace, channel):
    publish(client, workspace, graph())
    inbound(channel, "price", kind="comment", comment_id="c-4")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    inbound(channel, "no")
    run(state)
    sent = len(deliveries(channel))
    inbound(channel, "price again", kind="comment", comment_id="c-5")
    state.refresh_from_db()
    assert state.status == "completed"
    assert len(deliveries(channel)) == sent


def test_running_state_ignores_new_triggers(client, workspace, channel):
    publish(client, workspace, graph())
    inbound(channel, "price", kind="comment", comment_id="c-6")
    inbound(channel, "price", kind="comment", comment_id="c-7")
    assert ConversationState.objects.for_workspace(workspace).count() == 1
    run(ConversationState.objects.for_workspace(workspace).get())
    assert [d.recipient_id for d in deliveries(channel)] == ["c-6"]


def test_step_on_settled_state_is_a_noop(client, workspace, channel):
    publish(client, workspace, graph())
    inbound(channel, "price", kind="comment", comment_id="c-8")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    for _ in range(3):
        step(str(workspace.pk), str(state.id))
    assert len(deliveries(channel)) == 1


def test_delay_node_parks_state_until_due(client, workspace, channel):
    flow = graph(
        start="pause",
        nodes=[
            {"id": "pause", "data": {"kind": "delay", "seconds": 600}},
            {"id": "hello", "data": {"kind": "send_message", "text": "Hello"}},
            {"id": "done", "data": {"kind": "end"}},
        ],
        edges=[{"source": "pause", "target": "hello"}, {"source": "hello", "target": "done"}],
    )
    assert publish(client, workspace, flow).status_code == 200
    inbound(channel, "price", kind="comment", comment_id="c-9")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    assert state.status == "running" and state.node_id == "hello"
    assert state.available_at > timezone.now() + timedelta(seconds=590)
    assert deliveries(channel) == []


def test_execution_budget_stops_runaway_state(client, workspace, channel):
    publish(client, workspace, graph())
    inbound(channel, "price", kind="comment", comment_id="c-10")
    state = ConversationState.objects.for_workspace(workspace).get()
    state.steps = 100
    state.save()
    step(str(workspace.pk), str(state.id))
    state.refresh_from_db()
    assert (state.status, state.error_code) == ("stopped", "execution_guard")
    assert deliveries(channel) == []


def test_opt_out_stops_flow_and_blocks_sends(client, workspace, channel):
    publish(client, workspace, graph())
    inbound(channel, "price", kind="comment", comment_id="c-11")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    inbound(channel, "STOP")
    state.refresh_from_db()
    assert state.status == "waiting"  # STOP is not routed as the awaited answer
    state.status = "running"
    state.save()
    step(str(workspace.pk), str(state.id))
    state.refresh_from_db()
    assert state.status == "stopped"
    assert len(deliveries(channel)) == 1


def test_corrupt_state_fails_closed(client, workspace, channel):
    publish(client, workspace, graph())
    inbound(channel, "price", kind="comment", comment_id="c-12")
    state = ConversationState.objects.for_workspace(workspace).get()
    state.node_id = "missing"
    state.save()
    step(str(workspace.pk), str(state.id))
    state.refresh_from_db()
    assert state.status == "failed"
    assert deliveries(channel) == []


def test_closed_messaging_window_fails_flow_without_sending(client, workspace, channel):
    flow = graph(triggers=[{"kind": "dm", "keyword": "price"}])
    publish(client, workspace, flow)
    message = inbound(channel, "price")
    conversation = message.conversation
    conversation.last_inbound_at = timezone.now() - timedelta(hours=25)
    conversation.save()
    state = run(ConversationState.objects.for_workspace(workspace).get())
    assert state.status == "failed"
    assert deliveries(channel) == []


@pytest.mark.parametrize(
    "flow",
    [
        graph(edges=graph()["edges"] + [{"source": "done", "target": "offer"}]),
        graph(triggers=[]),
        graph(start="nowhere"),
        graph(
            nodes=graph()["nodes"] + [{"id": "orphan", "data": {"kind": "end"}}],
        ),
        graph(
            nodes=[
                {
                    "id": "offer",
                    "data": {
                        "kind": "send_buttons",
                        "text": "x",
                        "buttons": [{**BUTTON, "url": "http://insecure"}],
                    },
                },
                *graph()["nodes"][1:],
            ]
        ),
    ],
)
def test_invalid_flows_cannot_be_published(client, workspace, flow):
    assert publish(client, workspace, flow).status_code == 400


def test_agent_role_cannot_publish(workspace, channel):
    from rest_framework.test import APIClient

    from apps.tenants.models import Membership, User

    agent = User.objects.create_user(username="a", email="a@example.com")
    Membership.objects.for_workspace(workspace).create(workspace=workspace, user=agent)
    client = APIClient()
    client.force_authenticate(agent)
    response = client.post(
        f"/api/workspaces/{workspace.pk}/automations/",
        {"name": "x", "draft": graph()},
        format="json",
    )
    assert response.status_code == 403
