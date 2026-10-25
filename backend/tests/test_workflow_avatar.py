# ruff: noqa: F811 -- imported pytest fixtures are injected by parameter name.
import json
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.automations.avatar import create_video, execute_avatar
from apps.automations.models import ConversationState, WorkflowActionJob
from apps.automations.tasks import step
from apps.channels.models import Delivery
from apps.channels.transport import AmbiguousDelivery, RetryableError
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
    connection.is_test = False
    connection.save()
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="heygen",
        credentials=json.dumps({"api_key": "private-key"}),
        options={"avatar_id": "private-avatar", "voice_id": "saved-voice"},
    )
    graph = flow(
        {"kind": "avatar_video", "integration_id": str(config.pk), "text": "Welcome to our studio."}
    )
    graph["triggers"] = [{"kind": "dm", "keyword": "guide", "channel": "instagram"}]
    assert publish(client, workspace, graph).status_code == 200
    inbound(connection, "guide")
    state = ConversationState.objects.for_workspace(workspace).get()
    step(str(workspace.pk), str(state.pk))
    step(str(workspace.pk), str(state.pk))
    return state, WorkflowActionJob.objects.for_workspace(workspace).get(), config


def due(job):
    job.refresh_from_db()
    job.available_at = timezone.now()
    job.save()


def test_avatar_is_created_once_then_polled_and_delivered_once(client, workspace, channel):  # noqa: F811
    state, job, config = prepare(client, workspace, channel)
    with patch("apps.automations.avatar.create_video", return_value="video-one") as create:
        execute_avatar(str(workspace.pk), str(job.pk))
        execute_avatar(str(workspace.pk), str(job.pk))
    create.assert_called_once()
    job.refresh_from_db()
    assert job.status == "rendering"
    for status in ["processing", "completed"]:
        due(job)
        with patch(
            "apps.channels.transport.request",
            return_value={
                "data": {"status": status, "video_url": "https://files.heygen.ai/video/render.mp4"}
            },
        ) as poll:
            execute_avatar(str(workspace.pk), str(job.pk))
        assert poll.call_args.args[:2] == ("GET", "https://api.heygen.com/v3/videos/video-one")
    job.refresh_from_db()
    assert job.status == "complete"
    execute_avatar(str(workspace.pk), str(job.pk))
    assert Delivery.objects.for_workspace(workspace).filter(message__kind="video").count() == 1
    state.refresh_from_db()
    state.available_at = timezone.now()
    state.save()
    assert run(state).status == "completed"


def test_unknown_creation_is_never_automatically_replayed(client, workspace, channel):  # noqa: F811
    _, job, _ = prepare(client, workspace, channel)
    with patch("apps.automations.avatar.create_video", side_effect=AmbiguousDelivery()) as create:
        execute_avatar(str(workspace.pk), str(job.pk))
        execute_avatar(str(workspace.pk), str(job.pk))
    create.assert_called_once()
    job.refresh_from_db()
    assert job.status == "needs_review"


def test_retryable_poll_reuses_original_render_without_creating_again(client, workspace, channel):  # noqa: F811
    _, job, _ = prepare(client, workspace, channel)
    with patch("apps.automations.avatar.create_video", return_value="video-one"):
        execute_avatar(str(workspace.pk), str(job.pk))
    due(job)
    with patch("apps.channels.transport.request", side_effect=RetryableError(60)):
        execute_avatar(str(workspace.pk), str(job.pk))
    job.refresh_from_db()
    assert job.status == "rendering" and json.loads(job.result)["video_id"] == "video-one"
    assert job.available_at > timezone.now()


def test_current_heygen_api_contract_uses_selected_avatar_voice_and_script(workspace):
    config = IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="heygen",
        credentials=json.dumps({"api_key": "private-key"}),
        options={"avatar_id": "avatar", "voice_id": "voice"},
    )
    with patch(
        "apps.channels.transport.request", return_value={"data": {"video_id": "video-one"}}
    ) as provider:
        assert create_video(config, {"text": "Hello", "aspect_ratio": "9:16"}) == "video-one"
    assert provider.call_args.args == ("POST", "https://api.heygen.com/v3/videos")
    assert provider.call_args.kwargs["json"] == {
        "type": "avatar",
        "avatar_id": "avatar",
        "voice_id": "voice",
        "script": "Hello",
        "aspect_ratio": "9:16",
        "resolution": "720p",
    }
