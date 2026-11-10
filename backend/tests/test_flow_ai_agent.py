# ruff: noqa: F811 -- pytest fixtures imported from the runtime tests
"""The flow AI agent step: goal-driven replies until done or out of turns."""

import json
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.agents.models import AgentConfig, AgentRun, UsageRecord
from apps.agents.providers import Completion
from apps.automations.agent_step import parse_agent_output
from apps.automations.models import ConversationState, WorkflowActionJob
from apps.automations.preview import preview
from apps.automations.tasks import process_ai_job
from tests.conftest import set_limits
from tests.test_automation_runtime import (  # noqa: F401
    channel,
    deliveries,
    inbound,
    publish,
    quiet_notify,
    run,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def config(workspace):
    set_limits(workspace, ai_agent_enabled=True)
    return AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True
    )


def agent_flow(**agent):
    return {
        "start": "agent",
        "triggers": [{"kind": "dm", "keyword": "hello"}],
        "nodes": [
            {
                "id": "agent",
                "data": {
                    "kind": "ai_agent",
                    "prompt": "Qualify the lead: learn their budget and timeline.",
                    "persona": "Friendly and brief",
                    "max_turns": 3,
                    "use_knowledge": False,
                    **agent,
                },
            },
            {"id": "after", "data": {"kind": "send_message", "text": "A teammate will follow up."}},
            {"id": "end", "data": {"kind": "end"}},
        ],
        "edges": [{"source": "agent", "target": "after"}, {"source": "after", "target": "end"}],
    }


def texts(channel):
    return [json.loads(d.payload).get("text") for d in deliveries(channel)]


def due(state):
    """Skip the short poll delay the step sets while its reply is generated."""
    ConversationState.all_objects.filter(pk=state.pk).update(available_at=timezone.now())


def answer(workspace, state, text):
    """Settle the flow, letting a mocked model write the pending agent reply."""
    state = run(state)
    job = WorkflowActionJob.objects.for_workspace(workspace).filter(status="pending").first()
    if job:
        model = Mock()
        model.complete.return_value = Completion(text, [], 40, 10)
        with patch("apps.agents.providers.provider_for", return_value=model):
            process_ai_job(str(workspace.pk), str(job.pk))
        due(state)
        state = run(state)
        return state, model
    return state, None


def test_agent_converses_until_done_then_continues(client, workspace, channel, config):
    assert publish(client, workspace, agent_flow()).status_code == 200
    inbound(channel, "hello, interested in your service")
    state = ConversationState.objects.for_workspace(workspace).get()
    state, model = answer(
        workspace, state, '{"reply": "Great! What is your budget?", "done": false}'
    )
    assert state.status == "waiting" and state.node_id == "agent"
    prompt = model.complete.call_args.args[0]
    assert "Qualify the lead" in prompt[1]["content"]
    assert "Customer: hello, interested in your service" in prompt[1]["content"]
    assert "untrusted" in prompt[0]["content"]

    # The workspace agent does not also answer while the flow agent holds the thread.
    inbound(channel, "About $500, starting next month")
    assert not AgentRun.objects.for_workspace(workspace).exists()
    state, _ = answer(workspace, state, '{"reply": "Perfect, thanks!", "done": true}')
    assert state.status == "completed" and state.variables["agent_done"] is True
    assert texts(channel) == [
        "Great! What is your budget?",
        "Perfect, thanks!",
        "A teammate will follow up.",
    ]
    assert (
        UsageRecord.objects.for_workspace(workspace).filter(key__startswith="workflow:").count()
        == 2
    )


def test_agent_moves_on_after_max_turns(client, workspace, channel, config):
    assert publish(client, workspace, agent_flow(max_turns=1)).status_code == 200
    inbound(channel, "hello")
    state, _ = answer(
        workspace,
        ConversationState.objects.for_workspace(workspace).get(),
        '{"reply": "What is your budget?", "done": false}',
    )
    assert state.status == "completed" and state.variables["agent_done"] is False
    assert texts(channel)[-1] == "A teammate will follow up."


def test_invalid_agent_output_stops_for_review(client, workspace, channel, config):
    assert publish(client, workspace, agent_flow()).status_code == 200
    inbound(channel, "hello")
    state, _ = answer(
        workspace, ConversationState.objects.for_workspace(workspace).get(), "just text"
    )
    assert state.status == "failed"
    assert WorkflowActionJob.objects.for_workspace(workspace).get().status == "needs_review"


def test_local_test_provider_runs_the_agent(client, workspace, channel, config):
    assert publish(client, workspace, agent_flow()).status_code == 200
    inbound(channel, "hello")
    state = ConversationState.objects.for_workspace(workspace).get()
    run(state)
    job = WorkflowActionJob.objects.for_workspace(workspace).get()
    process_ai_job(str(workspace.pk), str(job.pk))
    due(state)
    state = run(state)
    assert state.status == "waiting"
    inbound(channel, "ok bye")
    run(state)
    job = WorkflowActionJob.objects.for_workspace(workspace).filter(status="pending").get()
    process_ai_job(str(workspace.pk), str(job.pk))
    due(state)
    assert run(state).status == "completed"


@pytest.mark.parametrize(
    "agent",
    [
        {"prompt": ""},
        {"max_turns": 0},
        {"max_turns": 21},
        {"persona": "x" * 1001},
        {"use_knowledge": "yes"},
    ],
)
def test_agent_validation(client, workspace, config, agent):
    assert publish(client, workspace, agent_flow(**agent)).status_code == 400


def test_agent_needs_ai_setup_to_publish(client, workspace):
    assert publish(client, workspace, agent_flow()).status_code in {400, 402}


def test_output_parsing_and_preview():
    assert parse_agent_output('ok {"reply": " Hi ", "done": false}') == {
        "reply": "Hi",
        "done": False,
        "captured": {},
    }
    assert parse_agent_output('{"reply": "", "done": true}') == {
        "reply": "",
        "done": True,
        "captured": {},
    }
    for bad in ['{"reply": "", "done": false}', '{"reply": 1, "done": true}', "nope"]:
        with pytest.raises(ValidationError):
            parse_agent_output(bad)
    trace = preview(agent_flow(), ["hello"], {})["trace"]
    assert trace[0]["detail"].startswith("Would chat with the lead toward: Qualify the lead")
    assert trace[1]["detail"] == "A teammate will follow up."


def test_agent_collects_details_onto_the_contact(client, workspace, channel, config):
    from apps.crm.models import Lead

    flow_ = agent_flow(capture_fields=["budget", "timeline"])
    assert publish(client, workspace, flow_).status_code == 200
    inbound(channel, "hello, I have about 500 dollars")
    state, model = answer(
        workspace,
        ConversationState.objects.for_workspace(workspace).get(),
        '{"reply": "When do you want to start?", "done": false,'
        ' "captured": {"budget": "500 USD", "timeline": null, "extra": "x"}}',
    )
    instruction = model.complete.call_args.args[0][0]["content"]
    assert '["budget", "timeline"]' in instruction
    lead = Lead.objects.for_workspace(workspace).get()
    assert lead.fields == {"budget": "500 USD"}
    assert state.variables["budget"] == "500 USD" and "timeline" not in state.variables


def test_capture_fields_are_validated(client, workspace, config):
    for bad in (["Bad Name"], ["a"] * 2, [f"f{i}" for i in range(11)], ["last_text"]):
        assert publish(client, workspace, agent_flow(capture_fields=bad)).status_code == 400
