from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.automations.models import ConversationState, WorkflowActionJob
from apps.automations.tasks import process_follow_job, step
from apps.channels.models import ChannelConnection, Delivery
from apps.crm.services import queue_reply
from tests.test_guided_automation import flow, inbound, publish, quiet_notify, run  # noqa: F401

pytestmark = pytest.mark.django_db
FOLLOW = "nemio:follow:test"


@pytest.fixture(name="channel")
def follow_channel(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id="follow-test",
        access_token="test",
        is_test=True,
        expires_at=timezone.now() + timedelta(days=30),
    )


def setup_gate(client, workspace, channel):
    graph = flow()
    graph["nodes"].insert(
        0,
        {
            "id": "follow",
            "data": {
                "kind": "follow_gate",
                "text": "Follow our account, then tap below.",
                "button_title": "I'm following",
                "expected_reply": FOLLOW,
            },
        },
    )
    graph["start"] = "follow"
    graph["edges"].insert(0, {"source": "follow", "target": "resources"})
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide", "comment")
    state = run(ConversationState.objects.for_workspace(workspace).get())
    assert state.status == "waiting"
    assert not WorkflowActionJob.objects.for_workspace(workspace).exists()
    return state


def verify(state, channel, following):
    inbound(channel, FOLLOW)
    step(str(state.workspace_id), str(state.pk))
    job = (
        WorkflowActionJob.objects.for_workspace(state.workspace_id).order_by("-created_at").first()
    )
    adapter = Mock()
    adapter.following_status.return_value = following
    with patch("apps.channels.adapters.adapter_for", return_value=adapter):
        process_follow_job(str(state.workspace_id), str(job.pk))
        process_follow_job(str(state.workspace_id), str(job.pk))
    assert adapter.following_status.call_count == 1
    state.refresh_from_db()
    state.available_at = timezone.now()
    state.save()
    return run(state)


def test_button_confirmation_does_not_bypass_a_false_provider_follow_check(
    client, workspace, channel
):
    state = setup_gate(client, workspace, channel)
    inbound(channel, FOLLOW, "comment")
    assert not WorkflowActionJob.objects.for_workspace(workspace).exists()
    assert verify(state, channel, False).status == "waiting"
    assert (
        Delivery.objects.for_workspace(workspace).count() == 2
    )  # Two follow prompts, no resources.
    assert verify(state, channel, True).status == "completed"
    assert Delivery.objects.for_workspace(workspace).count() == 3
    state.refresh_from_db()
    assert state.variables["following"] is True


def test_unknown_follow_status_stops_instead_of_unlocking_resources(client, workspace, channel):
    state = setup_gate(client, workspace, channel)
    assert verify(state, channel, None).status == "failed"
    assert Delivery.objects.for_workspace(workspace).count() == 1


def test_public_comments_do_not_open_an_unrestricted_private_message_window(
    client, workspace, channel
):
    state = setup_gate(client, workspace, channel)
    with pytest.raises(ValidationError, match="window has closed"):
        queue_reply(state.conversation, "A second private message", "must-not-send")


def test_instagram_follow_adapter_requires_an_actual_boolean_status(channel):
    from apps.channels.instagram import LiveInstagramAdapter
    from apps.channels.transport import ProviderError

    adapter = LiveInstagramAdapter(channel)
    with patch(
        "apps.channels.instagram.request", return_value={"is_user_follow_business": False}
    ) as request:
        assert adapter.following_status("person") is False
    assert request.call_args.kwargs["params"] == {"fields": "is_user_follow_business"}
    with patch("apps.channels.instagram.request", return_value={"is_user_follow_business": "true"}):
        with pytest.raises(ProviderError, match="follow_status_unavailable"):
            adapter.following_status("person")
