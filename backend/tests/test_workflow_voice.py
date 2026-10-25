# ruff: noqa: F811 -- imported pytest fixtures are injected by parameter name.
import base64
import json
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.automations.media_steps import execute_voice, synthesize
from apps.automations.models import ConversationState, WorkflowActionJob
from apps.automations.tasks import step
from apps.channels.models import Delivery
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
        workspace=workspace, provider="elevenlabs", is_test=True
    )
    graph = flow(
        {"kind": "generate_voice", "text": "Hello {{last_text}}", "integration_id": str(config.pk)}
    )
    graph["triggers"] = [{"kind": "dm", "keyword": "guide", "channel": "instagram"}]
    assert publish(client, workspace, graph).status_code == 200
    inbound(connection, "guide")
    state = ConversationState.objects.for_workspace(workspace).get()
    step(str(workspace.pk), str(state.pk))
    step(str(workspace.pk), str(state.pk))
    return state, WorkflowActionJob.objects.for_workspace(workspace).get()


def test_voice_waits_for_one_durable_job_and_queues_only_once(client, workspace, channel):  # noqa: F811
    state, job = prepare(client, workspace, channel)
    execute_voice(str(workspace.pk), str(job.pk))
    execute_voice(str(workspace.pk), str(job.pk))
    state.available_at = timezone.now()
    state.save()
    assert run(state).status == "completed"
    assert Delivery.objects.for_workspace(workspace).count() == 2
    assert (
        Delivery.objects.for_workspace(workspace).filter(message__text__isnull=False).count() == 2
    )


def test_voice_opt_out_cancels_before_a_paid_provider_call(client, workspace, channel):  # noqa: F811
    state, job = prepare(client, workspace, channel)
    lead = state.conversation.identity.lead
    lead.opted_out = True
    lead.save()
    with patch("apps.automations.media_steps.synthesize") as provider:
        execute_voice(str(workspace.pk), str(job.pk))
    provider.assert_not_called()
    job.refresh_from_db()
    assert job.status == "needs_review"
    assert Delivery.objects.for_workspace(workspace).count() == 1


@pytest.mark.parametrize("provider", ["elevenlabs", "inworld", "minimax"])
def test_voice_provider_contracts_use_fixed_endpoints_and_decoded_audio(workspace, provider):
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider=provider,
        credentials=json.dumps({"api_key": "private-key"}),
        options={"voice_id": "voice", "model": "configured-model"},
    )
    output = b"mp3-bytes"
    response = (
        output
        if provider == "elevenlabs"
        else json.dumps(
            {"audioContent": base64.b64encode(output).decode()}
            if provider == "inworld"
            else {"base_resp": {"status_code": 0}, "data": {"audio": output.hex()}}
        ).encode()
    )
    with patch("apps.agents.voice.bounded_bytes", return_value=response) as transport:
        assert synthesize(config, "Hello") == output
    args, kwargs = transport.call_args
    assert args[0] == "POST" and args[1].startswith(
        {
            "elevenlabs": "https://api.elevenlabs.io/",
            "inworld": "https://api.inworld.ai/",
            "minimax": "https://api.minimax.io/",
        }[provider]
    )
    assert (
        kwargs["json"].get("modelId", kwargs["json"].get("model", kwargs["json"].get("model_id")))
        == "configured-model"
    )
    assert "private-key" not in str(kwargs["json"])
