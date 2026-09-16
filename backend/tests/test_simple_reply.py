"""Simple reply mode: one grounded model call, no tools, beside the LangGraph agent."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.agents.models import AgentConfig, AgentRun, AgentSession, ToolCall, UsageRecord
from apps.agents.providers import Completion
from apps.agents.runtime import FALLBACK_REPLY, HANDOFF_REPLY
from apps.agents.tasks import process_run
from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
from apps.crm.services import receive

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def quiet_notify():
    with patch("apps.crm.services.notify"), patch("apps.crm.tasks.notify"):
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


@pytest.fixture
def config(workspace):
    return AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True, mode="simple", allowed_tools=["book_call"]
    )


def inbound(channel, text):
    event = WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id=f"evt-{WebhookEvent.all_objects.count()}",
        payload="{}",
        available_at=timezone.now(),
    )
    message = receive(event, {"sender_id": "lead-1", "text": text})
    conversation = message.conversation
    if not conversation.ai_enabled:
        conversation.ai_enabled = True
        conversation.save()
    run, _ = AgentRun.objects.for_workspace(channel.workspace_id).get_or_create(
        message=message, defaults={"workspace_id": channel.workspace_id}
    )
    return run


def run(agent_run, *completions):
    provider = MagicMock()
    provider.complete.side_effect = list(completions)
    with patch("apps.agents.simple.provider_for", return_value=provider):
        process_run(str(agent_run.workspace_id), str(agent_run.id))
    agent_run.refresh_from_db()
    return provider


def delivered(channel):
    return [
        __import__("json").loads(item.payload)["text"]
        for item in Delivery.objects.for_workspace(channel.workspace_id).order_by("created_at")
    ]


def test_simple_mode_is_one_grounded_call_without_tools(channel, config):
    agent_run = inbound(channel, "What are your opening hours?")
    provider = run(agent_run, Completion("We are open 9 to 5.", [], 30, 8))
    assert provider.complete.call_count == 1
    messages, tools = provider.complete.call_args.args
    assert tools == []
    assert messages[0]["role"] == "developer" and "never claim" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "What are your opening hours?"}
    assert not any("Classify" in str(m.get("content", "")) for m in messages)
    assert agent_run.status == "complete"
    assert delivered(channel) == ["We are open 9 to 5."]
    usage = UsageRecord.objects.for_workspace(channel.workspace_id).get(key=f"agent:{agent_run.id}")
    assert (usage.input_tokens, usage.output_tokens, usage.status) == (30, 8, "complete")
    assert not ToolCall.objects.for_workspace(channel.workspace_id).exists()
    assert not AgentSession.objects.for_workspace(channel.workspace_id).exists()


def test_simple_mode_rerun_reuses_the_checkpointed_reply(channel, config):
    agent_run = inbound(channel, "Do you ship abroad?")
    run(agent_run, Completion("Yes, worldwide.", [], 10, 5))
    AgentRun.all_objects.filter(pk=agent_run.pk).update(status="pending")
    provider = run(agent_run, Completion("Different answer", [], 10, 5))
    provider.complete.assert_not_called()
    assert delivered(channel) == ["Yes, worldwide."]


def test_simple_mode_ignores_stray_tool_calls(channel, config):
    agent_run = inbound(channel, "Book me for tomorrow")
    stray = Completion("", [{"name": "book_call", "arguments": "{}", "call_id": "c"}], 10, 5)
    run(agent_run, stray)
    assert delivered(channel) == [FALLBACK_REPLY]
    assert not ToolCall.objects.for_workspace(channel.workspace_id).exists()


def test_simple_mode_keeps_deterministic_handoff(channel, config):
    agent_run = inbound(channel, "I want to talk to a real person")
    provider = run(agent_run)
    provider.complete.assert_not_called()
    assert delivered(channel) == [HANDOFF_REPLY]
    conversation = agent_run.message.conversation
    conversation.refresh_from_db()
    assert (conversation.status, conversation.ai_enabled) == ("needs_human", False)


def test_mode_is_validated_at_the_api(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/agent/"
    body = {"name": "Helper", "is_test": True, "enabled": True, "mode": "simple"}
    response = client.put(url, body, format="json")
    assert response.status_code in {200, 201} and response.json()["mode"] == "simple"
    assert AgentConfig.objects.for_workspace(workspace).get().mode == "simple"
    assert client.put(url, {**body, "mode": "autopilot"}, format="json").status_code == 400
