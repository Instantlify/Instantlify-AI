import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.channels.transport import AmbiguousDelivery
from apps.crm.models import IntegrationJob
from apps.crm.tasks import dispatch_integrations, process_integration
from tests.conftest import set_limits
from tests.test_marketing_integrations import integration

pytestmark = pytest.mark.django_db
AGENT = "55555555-5555-4555-8555-555555555555"


def payload():
    return {
        "request_id": str(uuid.uuid4()),
        "name": "Helpful call agent",
        "instructions": "Answer product questions.",
        "first_message": "Hello, I am an AI assistant.",
        "model": "gpt-4.1",
        "voice_id": "voice_one",
    }


def create(client, workspace, provider="vapi"):
    config = integration(workspace, provider)
    url = f"/api/workspaces/{workspace.pk}/integrations/{config.pk}/call-agents/"
    data = payload()
    response = client.post(url, data, format="json")
    assert response.status_code == 202, response.content
    return (
        config,
        url,
        data,
        IntegrationJob.objects.for_workspace(workspace).get(pk=response.json()["id"]),
    )


def test_vapi_creation_is_idempotent_and_does_not_place_a_call(client, workspace):
    _, url, data, job = create(client, workspace)
    assert client.post(url, data, format="json").json()["id"] == str(job.pk)
    with patch("apps.agents.call_agents.request", return_value={"id": AGENT}) as send:
        process_integration(str(workspace.pk), str(job.pk))
        process_integration(str(workspace.pk), str(job.pk))
    send.assert_called_once()
    assert send.call_args.args == ("POST", "https://api.vapi.ai/assistant")
    assert send.call_args.kwargs["json"]["model"]["messages"][0]["content"] == data["instructions"]
    job.refresh_from_db()
    assert job.status == "complete" and json.loads(job.result)["agent_id"] == AGENT
    response = client.get(url)
    assert response.json()[0]["agent_id"] == AGENT
    assert "private-token" not in response.content.decode()
    data["instructions"] = "Different request"
    assert client.post(url, data, format="json").status_code == 400


def test_retell_creates_response_engine_agent_then_publishes(client, workspace):
    _, _, _, job = create(client, workspace, "retell")
    with patch(
        "apps.agents.call_agents.request",
        side_effect=[
            {"llm_id": "llm_one"},
            {"agent_id": "agent_one", "version": 0},
            {"accepted": True},
        ],
    ) as send:
        process_integration(str(workspace.pk), str(job.pk))
    assert [call.args[1] for call in send.call_args_list] == [
        "https://api.retellai.com/create-retell-llm",
        "https://api.retellai.com/create-agent",
        "https://api.retellai.com/publish-agent-version/agent_one",
    ]
    assert send.call_args_list[1].kwargs["json"]["response_engine"]["llm_id"] == "llm_one"
    assert send.call_args.kwargs["json"] == {"version": 0}
    job.refresh_from_db()
    assert job.status == "complete" and json.loads(job.result)["published"] is True


@pytest.mark.parametrize("phase", ["agent", "publish"])
def test_retell_partial_failure_preserves_ids_and_is_not_replayed(client, workspace, phase):
    _, url, data, job = create(client, workspace, "retell")
    responses = [{"llm_id": "llm_one"}]
    if phase == "publish":
        responses.append({"agent_id": "agent_one", "version": 0})
    responses.append(AmbiguousDelivery())
    with patch("apps.agents.call_agents.request", side_effect=responses) as send:
        process_integration(str(workspace.pk), str(job.pk))
        count = send.call_count
        process_integration(str(workspace.pk), str(job.pk))
        assert client.post(url, data, format="json").json()["id"] == str(job.pk)
    assert send.call_count == count
    job.refresh_from_db()
    assert job.status == "needs_review" and json.loads(job.result)["llm_id"] == "llm_one"
    if phase == "publish":
        assert json.loads(job.result)["agent_id"] == "agent_one"


def test_plan_downgrade_before_worker_execution_prevents_provider_creation(client, workspace):
    _, url, _, job = create(client, workspace)
    set_limits(workspace, ai_agent_enabled=False)
    assert client.post(url, payload(), format="json").status_code == 402
    with patch("apps.agents.call_agents.request") as send:
        process_integration(str(workspace.pk), str(job.pk))
    send.assert_not_called()
    job.refresh_from_db()
    assert job.status == "needs_review"


def test_worker_interruption_preserves_creation_checkpoints(client, workspace):
    _, _, _, job = create(client, workspace, "retell")
    job.status = "executing"
    job.available_at = timezone.now() - timedelta(minutes=6)
    job.result = json.dumps({"llm_id": "llm_one", "agent_id": "agent_one"})
    job.save()
    with patch("apps.crm.tasks.enqueue_once"):
        dispatch_integrations()
    job.refresh_from_db()
    assert job.status == "needs_review"
    assert json.loads(job.result) == {
        "llm_id": "llm_one",
        "agent_id": "agent_one",
        "error": "worker_interrupted",
    }
