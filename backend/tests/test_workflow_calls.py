# ruff: noqa: F811 -- imported pytest fixtures are injected by parameter name.
import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.automations.calls import call_outcome, create_call, execute_call, next_call_time
from apps.automations.models import ConversationState, WorkflowActionJob
from apps.automations.tasks import step
from apps.crm.models import IntegrationConfig
from tests.test_guided_automation import (  # noqa: F401
    channel,
    flow,
    inbound,
    publish,
    quiet_notify,
    run,
)

pytestmark = pytest.mark.django_db


def prepare(client, workspace, connection):
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace, provider="vapi", is_test=True
    )
    graph = flow(
        {"kind": "wait", "variable": "phone"},
        {"kind": "send_message", "text": "Reply Yes, call me to request a call."},
        {"kind": "wait", "expected_reply": "Yes, call me"},
        {
            "kind": "ai_call",
            "integration_id": str(config.pk),
            "consent_reply": "Yes, call me",
            "timezone": "UTC",
            "weekdays": list(range(7)),
            "call_start": "00:00",
            "call_end": "23:59",
        },
    )
    graph["triggers"] = [{"kind": "dm", "keyword": "guide", "channel": "instagram"}]
    assert publish(client, workspace, graph).status_code == 200
    inbound(connection, "guide")
    state = ConversationState.objects.for_workspace(workspace).get()
    assert run(state).status == "waiting"
    inbound(connection, "+15550100200")
    assert run(state).status == "waiting"
    inbound(connection, "Yes, call me")
    step(str(workspace.pk), str(state.pk))
    return state, WorkflowActionJob.objects.for_workspace(workspace).get()


def test_customer_request_creates_one_call_and_acceptance_is_not_completion(
    client, workspace, channel
):  # noqa: F811
    state, job = prepare(client, workspace, channel)
    with patch(
        "apps.automations.calls.create_call", return_value={"id": "call-1", "status": "accepted"}
    ) as provider:
        execute_call(str(workspace.pk), str(job.pk))
        execute_call(str(workspace.pk), str(job.pk))
    provider.assert_called_once()
    state.refresh_from_db()
    state.available_at = timezone.now()
    state.save()
    finished = run(state)
    assert finished.status == "completed"
    assert finished.variables["call_result"]["status"] == "accepted"
    assert "phone" not in json.loads(
        WorkflowActionJob.objects.for_workspace(workspace).get().result
    )


def test_opt_out_between_scheduling_and_execution_prevents_the_call(client, workspace, channel):  # noqa: F811
    state, job = prepare(client, workspace, channel)
    lead = state.conversation.identity.lead
    lead.opted_out = True
    lead.save()
    with patch("apps.automations.calls.create_call") as provider:
        execute_call(str(workspace.pk), str(job.pk))
    provider.assert_not_called()
    job.refresh_from_db()
    assert job.status == "needs_review"


def test_call_window_uses_local_weekdays_and_skips_the_weekend():
    data = {
        "timezone": "Asia/Karachi",
        "weekdays": [0, 1, 2, 3, 4],
        "call_start": "09:00",
        "call_end": "18:00",
    }
    assert next_call_time(data, datetime(2026, 10, 23, 14, 0, tzinfo=UTC)) == datetime(
        2026, 10, 26, 4, 0, tzinfo=UTC
    )
    assert next_call_time(data, datetime(2026, 10, 23, 5, 0, tzinfo=UTC)) == datetime(
        2026, 10, 23, 5, 0, tzinfo=UTC
    )


def test_wait_for_outcome_polls_without_recreating_call(client, workspace, channel):
    state, job = prepare(client, workspace, channel)
    payload = json.loads(job.payload)
    payload["wait_for_completion"] = True
    job.payload = json.dumps(payload)
    job.save()
    with patch(
        "apps.automations.calls.create_call", return_value={"id": "call-one", "status": "accepted"}
    ) as create:
        execute_call(str(workspace.pk), str(job.pk))
        job.refresh_from_db()
        assert job.status == "calling"
        job.available_at = timezone.now()
        job.save()
        with patch(
            "apps.automations.calls.call_outcome",
            return_value={
                "id": "call-one",
                "status": "ended",
                "summary": "Customer requested a quote.",
            },
        ):
            execute_call(str(workspace.pk), str(job.pk))
        execute_call(str(workspace.pk), str(job.pk))
    create.assert_called_once()
    job.refresh_from_db()
    assert job.status == "complete"
    state.refresh_from_db()
    state.available_at = timezone.now()
    state.save()
    assert run(state).variables["call_result"]["summary"] == "Customer requested a quote."


@pytest.mark.parametrize("provider", ["vapi", "retell"])
def test_call_outcome_reads_only_matching_call_and_excludes_transcripts(workspace, provider):
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace, provider=provider, credentials=json.dumps({"api_key": "private"})
    )
    response = {
        "id": "call-one",
        "call_id": "call-one",
        "status": "ended",
        "call_status": "ended",
        "transcript": "private words",
        "analysis": {"summary": "Done"},
        "call_analysis": {"call_summary": "Done"},
    }
    with patch("apps.channels.transport.request", return_value=response) as read:
        assert call_outcome(config, "call-one")["summary"] == "Done"
        assert "transcript" not in call_outcome(config, "call-one")
    assert read.call_args.args[0] == "GET"


@pytest.mark.parametrize("provider", ["vapi", "retell"])
def test_provider_calls_have_fixed_endpoints_and_explicit_caller_configuration(workspace, provider):
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider=provider,
        credentials=json.dumps({"api_key": "private-key"}),
        options={
            "agent_id": "saved-agent",
            "phone_number_id": "saved-number",
            "from_number": "+15550100300",
        },
    )
    with patch(
        "apps.channels.transport.request",
        return_value={"id": "vapi-call", "call_id": "retell-call"},
    ) as transport:
        result = create_call(config, {"phone": "+15550100200"}, "stable-key")
    assert result["status"] == "accepted"
    args, kwargs = transport.call_args
    assert args == (
        "POST",
        "https://api.vapi.ai/call"
        if provider == "vapi"
        else "https://api.retellai.com/v2/create-phone-call",
    )
    assert kwargs["side_effect"] is True
    if provider == "retell":
        assert kwargs["json"]["idempotency_key"] == "stable-key"
        assert kwargs["json"]["from_number"] == "+15550100300"
    else:
        assert kwargs["json"]["assistantId"] == "saved-agent"
        assert kwargs["json"]["phoneNumberId"] == "saved-number"
