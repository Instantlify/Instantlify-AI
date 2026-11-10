# ruff: noqa: F811 -- pytest fixtures imported from the runtime tests
"""Engine upgrades: rule conditions, long/random delays, reply timeouts, webchat triggers,
intent triggers and burst coalescing for the agent."""

import json
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from apps.agents.models import AgentConfig, AgentRun, UsageRecord
from apps.agents.providers import Completion
from apps.automations.conditions import evaluate, validate_condition
from apps.automations.intents import parse_choice
from apps.automations.models import ConversationState, IntentMatch
from apps.automations.preview import preview
from apps.automations.tasks import dispatch_runs, process_intent_match, wait_timed_out
from apps.crm.models import Lead
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


def flow(nodes, edges, start="first", triggers=None):
    return {
        "start": start,
        "triggers": triggers or [{"kind": "dm", "keyword": "hello"}],
        "nodes": nodes,
        "edges": edges,
    }


def branch_flow(condition):
    return flow(
        [
            {"id": "first", "data": {"kind": "condition", **condition}},
            {"id": "yes", "data": {"kind": "send_message", "text": "YES"}},
            {"id": "no", "data": {"kind": "send_message", "text": "NO"}},
            {"id": "end", "data": {"kind": "end"}},
        ],
        [
            {"source": "first", "target": "yes", "sourceHandle": "true"},
            {"source": "first", "target": "no", "sourceHandle": "false"},
            {"source": "yes", "target": "end"},
            {"source": "no", "target": "end"},
        ],
    )


def sent_texts(channel):
    return [json.loads(d.payload).get("text") for d in deliveries(channel)]


# --- conditions


def ctx(**overrides):
    base = {
        "variables": {"last_text": "Hello, what's the PRICE?", "budget": "750"},
        "fields": {"plan": "Pro"},
        "tags": ["VIP", "lead_magnet"],
        "stage": "qualified",
        "email": "",
        "channel": "instagram",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "rule,expected",
    [
        (
            {"subject": "variable", "name": "last_text", "operator": "contains", "value": "price"},
            True,
        ),
        (
            {
                "subject": "variable",
                "name": "last_text",
                "operator": "starts_with",
                "value": "hello",
            },
            True,
        ),
        (
            {"subject": "variable", "name": "last_text", "operator": "ends_with", "value": "nope"},
            False,
        ),
        (
            {"subject": "variable", "name": "budget", "operator": "greater_than", "value": "500"},
            True,
        ),
        ({"subject": "variable", "name": "budget", "operator": "less_than", "value": "500"}, False),
        (
            {"subject": "variable", "name": "missing", "operator": "greater_than", "value": "1"},
            False,
        ),
        ({"subject": "field", "name": "plan", "operator": "equals", "value": "pro"}, True),
        ({"subject": "field", "name": "plan", "operator": "not_equals", "value": "pro"}, False),
        ({"subject": "tag", "operator": "contains", "value": "vip"}, True),
        ({"subject": "tag", "operator": "not_contains", "value": "vip"}, False),
        ({"subject": "tag", "operator": "is_set"}, True),
        ({"subject": "stage", "operator": "equals", "value": "qualified"}, True),
        ({"subject": "email", "operator": "is_not_set"}, True),
        ({"subject": "channel", "operator": "equals", "value": "whatsapp"}, False),
    ],
)
def test_condition_rules(rule, expected):
    validate_condition({"rules": [rule]})
    assert evaluate({"rules": [rule]}, ctx()) is expected


def test_condition_all_and_any_and_legacy_shape():
    rules = [
        {"subject": "tag", "operator": "contains", "value": "vip"},
        {"subject": "stage", "operator": "equals", "value": "won"},
    ]
    assert evaluate({"match": "all", "rules": rules}, ctx()) is False
    assert evaluate({"match": "any", "rules": rules}, ctx()) is True
    # Flows saved before rules existed keep their case-insensitive equality meaning.
    assert evaluate({"variable": "budget", "equals": "750"}, ctx()) is True
    assert evaluate({"variable": "budget", "equals": "751"}, ctx()) is False


@pytest.mark.parametrize(
    "data",
    [
        {"rules": []},
        {"rules": [{"subject": "nope", "operator": "equals"}]},
        {"rules": [{"subject": "tag", "operator": "greater_than", "value": "1"}]},
        {"rules": [{"subject": "variable", "name": "x y", "operator": "equals"}]},
        {"rules": [{"subject": "variable", "name": "x", "operator": "less_than", "value": "abc"}]},
        {"rules": [{"subject": "tag", "operator": "contains", "value": " "}]},
        {"match": "some", "rules": [{"subject": "email", "operator": "is_set"}]},
    ],
)
def test_invalid_conditions_are_rejected(data):
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        validate_condition(data)


def test_condition_reads_the_live_contact_at_runtime(client, workspace, channel):
    flow_ = branch_flow({"rules": [{"subject": "tag", "operator": "contains", "value": "VIP"}]})
    assert publish(client, workspace, flow_).status_code == 200
    inbound(channel, "hello")
    run(ConversationState.objects.for_workspace(workspace).get())
    assert sent_texts(channel) == ["NO"]

    lead = Lead.objects.for_workspace(workspace).get()
    lead.tags = ["vip"]
    lead.save()
    state = ConversationState.objects.for_workspace(workspace).get()
    state.cooldown_until = None
    state.save()
    inbound(channel, "hello again")
    run(ConversationState.objects.for_workspace(workspace).get())
    assert sent_texts(channel)[-1] == "YES"


def test_preview_explains_and_evaluates_rules():
    result = preview(
        branch_flow(
            {"match": "all", "rules": [{"subject": "tag", "operator": "contains", "value": "vip"}]}
        ),
        ["hello"],
        {"contact": {"tags": ["VIP"]}},
    )
    assert result["trace"][0]["detail"] == "has tag “vip” · true branch"
    assert result["trace"][1]["detail"] == "YES"


# --- delays


def delay_flow(data):
    return flow(
        [
            {"id": "first", "data": {"kind": "delay", **data}},
            {"id": "msg", "data": {"kind": "send_message", "text": "Later"}},
            {"id": "end", "data": {"kind": "end"}},
        ],
        [{"source": "first", "target": "msg"}, {"source": "msg", "target": "end"}],
    )


def test_delay_can_wait_days_and_random_window_is_deterministic(client, workspace, channel):
    assert publish(client, workspace, delay_flow({"seconds": 7 * 86400})).status_code == 200
    inbound(channel, "hello")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    assert state.available_at > timezone.now() + timedelta(days=6, hours=23)

    from apps.automations.services import delay_seconds

    state.node_id = "first"
    picks = {delay_seconds(state, {"seconds": 60, "seconds_max": 120}) for _ in range(5)}
    assert len(picks) == 1 and 60 <= picks.pop() <= 120


@pytest.mark.parametrize(
    "data",
    [
        {"seconds": 0},
        {"seconds": 31 * 86400},
        {"seconds": 60, "seconds_max": 30},
        {"seconds": True},
    ],
)
def test_invalid_delays_are_rejected(client, workspace, data):
    assert publish(client, workspace, delay_flow(data)).status_code == 400


# --- reply timeout


def timeout_flow(timeout=3600):
    return flow(
        [
            {"id": "first", "data": {"kind": "send_message", "text": "Want the guide?"}},
            {
                "id": "ask",
                "data": {"kind": "wait", "variable": "answer", "timeout_seconds": timeout},
            },
            {"id": "thanks", "data": {"kind": "send_message", "text": "Thanks {{answer}}"}},
            {"id": "nudge", "data": {"kind": "send_message", "text": "Still there?"}},
            {"id": "end", "data": {"kind": "end"}},
        ],
        [
            {"source": "first", "target": "ask"},
            {"source": "ask", "target": "thanks"},
            {"source": "ask", "target": "nudge", "sourceHandle": "timeout"},
            {"source": "thanks", "target": "end"},
            {"source": "nudge", "target": "end"},
        ],
    )


def test_wait_takes_timeout_path_when_no_reply_arrives(client, workspace, channel):
    assert publish(client, workspace, timeout_flow()).status_code == 200
    inbound(channel, "hello")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    assert state.status == "waiting" and state.timeout_at is not None

    # Not due yet: nothing happens.
    wait_timed_out(str(workspace.pk), str(state.pk))
    state.refresh_from_db()
    assert state.status == "waiting"

    state.timeout_at = timezone.now() - timedelta(seconds=1)
    state.save()
    with patch("apps.automations.tasks.enqueue_once") as enqueue:
        dispatch_runs()
    assert any(call.args[0] is wait_timed_out for call in enqueue.call_args_list)
    wait_timed_out(str(workspace.pk), str(state.pk))
    state = run(state)
    assert state.status == "completed" and state.variables["timed_out"] is True
    assert sent_texts(channel)[-1] == "Still there?"


def test_reply_before_timeout_takes_reply_path(client, workspace, channel):
    assert publish(client, workspace, timeout_flow()).status_code == 200
    inbound(channel, "hello")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    inbound(channel, "yes please")
    state = run(state)
    assert state.status == "completed" and state.timeout_at is None
    assert sent_texts(channel)[-1] == "Thanks yes please"


def test_timeout_wait_needs_both_paths(client, workspace):
    bad = timeout_flow()
    bad["edges"] = [e for e in bad["edges"] if e.get("sourceHandle") != "timeout"]
    bad["nodes"] = [n for n in bad["nodes"] if n["id"] != "nudge"]
    assert publish(client, workspace, bad).status_code == 400
    assert publish(client, workspace, timeout_flow(timeout=10)).status_code == 400


# --- webchat


def test_webchat_messages_can_trigger_flows(client, workspace):
    from rest_framework.test import APIClient

    graph = flow(
        [
            {"id": "first", "data": {"kind": "send_message", "text": "Hi from the flow"}},
            {"id": "end", "data": {"kind": "end"}},
        ],
        [{"source": "first", "target": "end"}],
        triggers=[{"kind": "dm", "keyword": "pricing", "channel": "webchat"}],
    )
    assert publish(client, workspace, graph).status_code == 200
    visitor = APIClient()
    url = f"/api/public/webchat/{workspace.pk}/"
    assert (
        visitor.post(
            url, {"visitor": "visitor-abc1", "text": "pricing?"}, format="json"
        ).status_code
        == 201
    )
    state = run(ConversationState.objects.for_workspace(workspace).get())
    assert state.status == "completed"
    texts = [m["text"] for m in visitor.get(url, {"visitor": "visitor-abc1"}).json()["messages"]]
    assert texts == ["pricing?", "Hi from the flow"]


# --- intent triggers


@pytest.fixture
def config(workspace):
    set_limits(workspace, ai_agent_enabled=True)
    return AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True
    )


def enable_ai(channel):
    """Open the conversation and switch its AI agent on (conversations start with it off)."""
    from apps.crm.models import Conversation

    inbound(channel, "hey")
    Conversation.objects.for_workspace(channel.workspace_id).update(ai_enabled=True)
    AgentRun.objects.for_workspace(channel.workspace_id).delete()


def intent_flow():
    return flow(
        [
            {"id": "first", "data": {"kind": "send_message", "text": "Our plans start at $20"}},
            {"id": "end", "data": {"kind": "end"}},
        ],
        [{"source": "first", "target": "end"}],
        triggers=[{"kind": "dm", "keyword": "asks how much it costs", "match": "intent"}],
    )


def classify_with(workspace, job, text):
    model = Mock()
    model.complete.return_value = Completion(text, [], 30, 4)
    with patch("apps.agents.providers.provider_for", return_value=model):
        process_intent_match(str(workspace.pk), str(job.pk))
        process_intent_match(str(workspace.pk), str(job.pk))
    assert model.complete.call_count == 1
    job.refresh_from_db()
    return job, model


def test_intent_trigger_starts_flow_when_model_matches(client, workspace, channel, config):
    assert publish(client, workspace, intent_flow()).status_code == 200
    message = inbound(channel, "how expensive is this thing")
    # No keyword appears, so the message waits for intent matching, not the agent.
    job = IntentMatch.objects.for_workspace(workspace).get(message=message)
    assert not AgentRun.objects.for_workspace(workspace).exists()

    job, model = classify_with(workspace, job, '{"match": 1}')
    assert job.status == "matched"
    prompt = model.complete.call_args.args[0]
    assert "1. asks how much it costs" in prompt[0]["content"]
    assert prompt[1] == {"role": "user", "content": "how expensive is this thing"}
    run(ConversationState.objects.for_workspace(workspace).get())
    assert sent_texts(channel) == ["Our plans start at $20"]
    usage = UsageRecord.objects.for_workspace(workspace).get(key=f"intent:{job.pk}")
    assert usage.status == "complete" and usage.input_tokens == 30


@pytest.mark.parametrize("answer", ['{"match": null}', "not json", '{"match": 7}'])
def test_no_intent_or_bad_answer_falls_back_to_the_agent(
    client, workspace, channel, config, answer
):
    enable_ai(channel)
    assert publish(client, workspace, intent_flow()).status_code == 200
    message = inbound(channel, "do you ship to Canada")
    job, _ = classify_with(workspace, IntentMatch.objects.for_workspace(workspace).get(), answer)
    assert job.status in {"no_match", "failed"}
    assert not ConversationState.objects.for_workspace(workspace).exists()
    assert AgentRun.objects.for_workspace(workspace).filter(message=message).exists()


def test_keyword_triggers_win_before_intent_matching(client, workspace, channel, config):
    assert publish(client, workspace, intent_flow()).status_code == 200
    keyword = flow(
        [
            {"id": "first", "data": {"kind": "send_message", "text": "Keyword flow"}},
            {"id": "end", "data": {"kind": "end"}},
        ],
        [{"source": "first", "target": "end"}],
        triggers=[{"kind": "dm", "keyword": "expensive"}],
    )
    assert publish(client, workspace, keyword).status_code == 200
    inbound(channel, "how expensive is it")
    assert not IntentMatch.objects.for_workspace(workspace).exists()
    run(ConversationState.objects.for_workspace(workspace).get())
    assert sent_texts(channel) == ["Keyword flow"]


def test_without_ai_configuration_intent_triggers_do_not_block_the_agent(
    client, workspace, channel
):
    enable_ai(channel)
    assert publish(client, workspace, intent_flow()).status_code == 200
    message = inbound(channel, "how expensive is this")
    assert not IntentMatch.objects.for_workspace(workspace).exists()
    assert AgentRun.objects.for_workspace(workspace).filter(message=message).exists()


def test_intent_validation_and_choice_parsing(client, workspace):
    bad = intent_flow()
    bad["triggers"][0]["keyword"] = "*"
    assert publish(client, workspace, bad).status_code == 400
    bad["triggers"][0].update(keyword="price", match="regex")
    assert publish(client, workspace, bad).status_code == 400
    assert parse_choice('{"match": 2}', 3) == 1
    assert parse_choice('Sure: {"match": null}', 3) is None
    for text in ['{"match": true}', '{"match": 0}', '{"match": 1, "x": 2}']:
        with pytest.raises(ValueError):
            parse_choice(text, 3)


def test_local_test_provider_matches_intents_by_shared_words(client, workspace, channel, config):
    assert publish(client, workspace, intent_flow()).status_code == 200
    inbound(channel, "what does it costs")
    job = IntentMatch.objects.for_workspace(workspace).get()
    process_intent_match(str(workspace.pk), str(job.pk))
    job.refresh_from_db()
    assert job.status == "matched"


# --- agent burst coalescing


def test_older_pending_agent_run_is_superseded_by_a_newer_message(workspace, channel, config):
    from apps.agents.tasks import process_run

    enable_ai(channel)
    first = inbound(channel, "hi")
    second = inbound(channel, "are you there?")
    with patch("apps.agents.simple.run_simple"), patch("apps.agents.runtime.run_agent") as agent:
        process_run(
            str(workspace.pk), str(AgentRun.objects.for_workspace(workspace).get(message=first).pk)
        )
        assert AgentRun.objects.for_workspace(workspace).get(message=first).status == "superseded"
        agent.assert_not_called()
        process_run(
            str(workspace.pk), str(AgentRun.objects.for_workspace(workspace).get(message=second).pk)
        )
    assert AgentRun.objects.for_workspace(workspace).get(message=second).status == "complete"
    agent.assert_called_once()


def test_reply_delay_waits_for_the_customer_to_finish(workspace, channel, config):
    from apps.agents.tasks import process_run

    config.reply_delay_seconds = 10
    config.save()
    enable_ai(channel)
    message = inbound(channel, "hi")
    run_ = AgentRun.objects.for_workspace(workspace).get(message=message)
    with patch("apps.agents.runtime.run_agent") as agent:
        process_run(str(workspace.pk), str(run_.pk))
        run_.refresh_from_db()
        assert run_.status == "pending"
        agent.assert_not_called()
        message.created_at = timezone.now() - timedelta(seconds=11)
        message.save()
        process_run(str(workspace.pk), str(run_.pk))
    run_.refresh_from_db()
    assert run_.status == "complete"
