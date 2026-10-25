import json
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from apps.agents.models import AgentConfig, UsageRecord
from apps.agents.providers import Completion
from apps.automations.models import ConversationState, WorkflowActionJob
from apps.automations.tasks import dispatch_runs, process_ai_job, step
from apps.channels.models import ChannelConnection
from apps.crm.models import Lead
from tests.conftest import set_limits
from tests.test_guided_automation import (  # noqa: F401
    flow,
    inbound,
    publish,
    quiet_notify,
    run,
)

pytestmark = pytest.mark.django_db


def test_local_test_provider_returns_unknown_extraction_and_a_fixed_decision():
    from apps.agents.providers import FakeLLMProvider

    provider = FakeLLMProvider()
    extraction = provider.complete(
        [
            {
                "role": "developer",
                "content": 'Extract only these fields as a JSON object: ["name", "email"]. Use null for unknown values; do not invent data.',
            }
        ],
        [],
    )
    decision = provider.complete(
        [
            {
                "role": "developer",
                "content": 'Evaluate the user condition. Return only {"result":true} or {"result":false} as JSON.',
            }
        ],
        [],
    )
    assert json.loads(extraction.text) == {"name": None, "email": None}
    assert json.loads(decision.text) == {"result": False}


@pytest.fixture(name="channel")
def workflow_channel(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id="ai-workflow-test",
        access_token="test",
        is_test=True,
        expires_at=timezone.now() + timedelta(days=30),
    )


@pytest.fixture
def config(workspace):
    set_limits(workspace, ai_agent_enabled=True)
    return AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True
    )


def start_job(client, workspace, channel, data):
    graph = flow(data, {"kind": "set_field", "field": "result", "value": "{{ai_result}}"})
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide", "comment")
    state = ConversationState.objects.for_workspace(workspace).get()
    step(str(workspace.pk), str(state.pk))
    step(str(workspace.pk), str(state.pk))
    return state, WorkflowActionJob.objects.for_workspace(workspace).get()


def complete(workspace, state, job, text):
    model = Mock()
    model.complete.return_value = Completion(text, [], 12, 18)
    with patch("apps.agents.providers.provider_for", return_value=model):
        process_ai_job(str(workspace.pk), str(job.pk))
        process_ai_job(str(workspace.pk), str(job.pk))
    assert model.complete.call_count == 1
    state.available_at = timezone.now()
    state.save()
    return run(state)


def test_generation_waits_for_one_metered_job_and_reuses_its_result(
    client, workspace, channel, config
):
    state, job = start_job(
        client, workspace, channel, {"kind": "ai_generate", "prompt": "Summarize {{last_text}}"}
    )
    assert json.loads(job.payload)["prompt"] == "Summarize guide"
    assert WorkflowActionJob.objects.for_workspace(workspace).count() == 1
    assert complete(workspace, state, job, "A guide enquiry").status == "completed"
    assert Lead.objects.for_workspace(workspace).get().fields["result"] == "A guide enquiry"
    usage = UsageRecord.objects.for_workspace(workspace).get(key=f"workflow:{job.pk}")
    assert usage.status == "complete" and usage.calls == 1 and usage.input_tokens == 12


def test_extraction_produces_only_requested_scalar_variables(client, workspace, channel, config):
    state, job = start_job(
        client,
        workspace,
        channel,
        {
            "kind": "ai_extract",
            "prompt": "Extract details from {{last_text}}",
            "fields": ["email", "budget"],
        },
    )
    assert complete(workspace, state, job, '{"email":null,"budget":500}').status == "completed"
    state.refresh_from_db()
    assert state.variables["email"] is None and state.variables["budget"] == 500


@pytest.mark.parametrize(
    "text", ['{"result":"true"}', '```json\n{"result":true}\n```', '{"email":{"nested":"value"}}']
)
def test_invalid_ai_decisions_stop_for_review_without_automatic_retry(
    client, workspace, channel, config, text
):
    state, job = start_job(
        client,
        workspace,
        channel,
        {"kind": "ai_extract", "prompt": "Extract email", "fields": ["email"]},
    )
    assert complete(workspace, state, job, text).status == "failed"
    job.refresh_from_db()
    assert job.status == "needs_review"
    assert UsageRecord.objects.for_workspace(workspace).get().calls == 1


@pytest.mark.parametrize("decision", [True, False])
def test_ai_condition_takes_exactly_one_validated_branch(
    client, workspace, channel, config, decision
):
    graph = {
        "start": "decision",
        "triggers": [{"kind": "dm", "keyword": "guide", "channel": "instagram"}],
        "nodes": [
            {
                "id": "decision",
                "data": {
                    "kind": "ai_condition",
                    "prompt": "Is this a guide request? {{last_text}}",
                },
            },
            {"id": "yes", "data": {"kind": "set_stage", "stage": "qualified"}},
            {"id": "no", "data": {"kind": "set_stage", "stage": "lost"}},
            {"id": "end", "data": {"kind": "end"}},
        ],
        "edges": [
            {"source": "decision", "target": "yes", "sourceHandle": "true"},
            {"source": "decision", "target": "no", "sourceHandle": "false"},
            {"source": "yes", "target": "end"},
            {"source": "no", "target": "end"},
        ],
    }
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide")
    state = ConversationState.objects.for_workspace(workspace).get()
    step(str(workspace.pk), str(state.pk))
    job = WorkflowActionJob.objects.for_workspace(workspace).get()
    assert complete(workspace, state, job, json.dumps({"result": decision})).status == "completed"
    assert Lead.objects.for_workspace(workspace).get().stage == (
        "qualified" if decision else "lost"
    )


def test_opt_out_before_ai_execution_blocks_model_and_credit_use(
    client, workspace, channel, config
):
    state, job = start_job(client, workspace, channel, {"kind": "ai_generate", "prompt": "Help"})
    Lead.objects.for_workspace(workspace).update(opted_out=True)
    with patch("apps.agents.providers.provider_for") as provider:
        process_ai_job(str(workspace.pk), str(job.pk))
    provider.assert_not_called()
    assert not UsageRecord.objects.for_workspace(workspace).exists()


def test_interrupted_ai_job_requires_review_instead_of_calling_model_again(
    client, workspace, channel, config
):
    state, job = start_job(client, workspace, channel, {"kind": "ai_generate", "prompt": "Help"})
    job.status, job.available_at = "executing", timezone.now() - timedelta(minutes=6)
    job.save()
    with patch("apps.automations.tasks.enqueue_once"):
        dispatch_runs()
    job.refresh_from_db()
    assert job.status == "needs_review" and job.error_code == "worker_interrupted"


def test_byo_key_cannot_select_another_provider(client, workspace, channel, config):
    config.billing_mode, config.provider, config.model = "byo_key", "openai", "custom-model"
    config.save()
    response = publish(
        client,
        workspace,
        flow(
            {
                "kind": "ai_generate",
                "prompt": "Help",
                "ai_provider": "gemini",
                "ai_model": "gemini-2.5-flash",
            }
        ),
    )
    assert response.status_code == 400
