"""Every inbound message is checked for escalation before any automation runs."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.agents.models import AgentConfig, AgentRun
from apps.automations.models import Automation, ConversationState
from apps.automations.services import publish
from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
from apps.crm.services import receive
from apps.crm.triage import triage_inbound

pytestmark = pytest.mark.django_db


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


def inbound(channel, text):
    event = WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id=f"evt-{WebhookEvent.all_objects.count()}",
        payload="{}",
        available_at=timezone.now(),
    )
    return receive(event, {"sender_id": "lead-1", "text": text, "kind": "dm"})


def price_flow(workspace, user):
    automation = Automation.objects.for_workspace(workspace).create(workspace=workspace, name="x")
    publish(
        automation,
        {
            "start": "hi",
            "triggers": [{"kind": "dm", "keyword": "price"}],
            "nodes": [
                {"id": "hi", "data": {"kind": "send_message", "text": "Prices!"}},
                {"id": "end", "data": {"kind": "end"}},
            ],
            "edges": [{"source": "hi", "target": "end"}],
        },
        user,
    )


def test_angry_message_matching_a_trigger_goes_to_a_human_not_the_flow(channel, workspace, user):
    price_flow(workspace, user)
    message = inbound(channel, "I demand a refund immediately, your price is a scam")
    conversation = message.conversation
    conversation.refresh_from_db()
    assert conversation.status == "needs_human" and not conversation.ai_enabled
    assert not ConversationState.objects.for_workspace(workspace).exists()
    assert not AgentRun.objects.for_workspace(workspace).exists()
    # No bot was talking here, so nothing automated replies; a person answers.
    assert not Delivery.objects.for_workspace(workspace).exists()


def test_clean_message_still_triggers_the_flow(channel, workspace, user):
    price_flow(workspace, user)
    message = inbound(channel, "What is the price?")
    assert ConversationState.objects.for_workspace(workspace).get().status == "running"
    message.conversation.refresh_from_db()
    assert message.conversation.status != "needs_human"


def test_escalation_stops_a_flow_waiting_for_an_answer(channel, workspace, user):
    automation = Automation.objects.for_workspace(workspace).create(workspace=workspace, name="q")
    publish(
        automation,
        {
            "start": "ask",
            "triggers": [{"kind": "dm", "keyword": "price"}],
            "nodes": [
                {"id": "ask", "data": {"kind": "wait", "variable": "size"}},
                {"id": "end", "data": {"kind": "end"}},
            ],
            "edges": [{"source": "ask", "target": "end"}],
        },
        user,
    )
    first = inbound(channel, "price")
    state = ConversationState.objects.for_workspace(workspace).get()
    state.status = "waiting"
    state.save()
    inbound(channel, "Forget it, I want to speak to a human")
    state.refresh_from_db()
    assert (state.status, state.error_code) == ("stopped", "handoff")
    first.conversation.refresh_from_db()
    assert first.conversation.status == "needs_human"


@pytest.mark.parametrize(
    "text,escalates",
    [
        ("Is this refundable?", False),  # whole words only
        ("I'd love the scampi", False),
        ("Are you a travel agent?", False),  # bare "agent"/"human" never escalate
        ("I work in human resources", False),
        ("Please REFUND me", True),
        ("can I talk to a human", True),
        ("This is fraud.", True),
    ],
)
def test_phrase_matching(channel, text, escalates):
    message = inbound(channel, "hello")
    message.text = text
    assert triage_inbound(message).escalate is escalates


def test_workspace_keywords_and_switch_are_respected(channel, workspace):
    message = inbound(channel, "hello")
    config = AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, handoff_keywords=["unacceptable"]
    )
    message.text = "This is unacceptable"
    assert triage_inbound(message).matched == "unacceptable"
    message.text = "I want a refund"  # the workspace replaced the defaults
    assert not triage_inbound(message).escalate
    config.triage_enabled = False
    config.save()
    message.text = "This is unacceptable"
    assert not triage_inbound(message).escalate
