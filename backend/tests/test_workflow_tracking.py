import json
from datetime import timedelta
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics.models import FunnelEvent
from apps.automations.models import ConversationState, WorkflowLink
from apps.automations.tasks import step
from apps.channels.models import ChannelConnection, Delivery
from apps.channels.tasks import send_delivery
from tests.test_guided_automation import flow, inbound, publish, quiet_notify, run  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(name="channel")
def tracking_channel(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id="tracking-test",
        access_token="test",
        is_test=True,
        expires_at=timezone.now() + timedelta(days=30),
    )


def prepare(client, workspace, channel):
    graph = flow(
        {"kind": "delay", "seconds": 60},
        {"kind": "send_reminder", "text": "Did you open the guide?", "source_node": "resources"},
    )
    graph["triggers"] = [{"kind": "dm", "keyword": "guide", "channel": "instagram"}]
    graph["nodes"][0]["data"]["track_clicks"] = True
    assert publish(client, workspace, graph).status_code == 200
    inbound(channel, "guide")
    state = ConversationState.objects.for_workspace(workspace).get()
    step(str(workspace.pk), str(state.pk))
    step(str(workspace.pk), str(state.pk))
    state.refresh_from_db()
    assert state.node_id == "action-1" and state.available_at > timezone.now()
    return state, WorkflowLink.objects.for_workspace(workspace).get()


def finish(state):
    state.available_at = timezone.now()
    state.save()
    return run(state)


def test_tracked_resource_uses_an_opaque_token_and_redirect_records_once(
    client, workspace, channel
):
    state, link = prepare(client, workspace, channel)
    delivery = Delivery.objects.for_workspace(workspace).get()
    url = json.loads(delivery.payload)["buttons"][0]["url"]
    assert urlsplit(url).path == f"/r/{link.code}/"
    assert str(state.pk) not in url and str(workspace.pk) not in url
    visitor = APIClient()
    assert visitor.head(urlsplit(url).path).status_code == 302
    link.refresh_from_db()
    assert link.clicked_at is None
    for _ in range(2):
        response = visitor.get(urlsplit(url).path)
        assert response.status_code == 302 and response["Location"] == "https://example.com/guide"
    assert (
        FunnelEvent.objects.for_workspace(workspace)
        .filter(kind="link_click", automation_id=state.automation_id)
        .count()
        == 1
    )
    assert finish(state).status == "completed"
    assert Delivery.objects.for_workspace(workspace).count() == 1


def test_unclicked_resource_queues_a_single_reminder(client, workspace, channel):
    state, link = prepare(client, workspace, channel)
    assert finish(state).status == "completed"
    assert Delivery.objects.for_workspace(workspace).count() == 2
    reminder = Delivery.objects.for_workspace(workspace).order_by("-created_at").first()
    assert json.loads(reminder.payload)["unless_clicked"]["run_token"] == str(state.run_token)
    step(str(workspace.pk), str(state.pk))
    assert Delivery.objects.for_workspace(workspace).count() == 2


def test_a_click_after_queueing_still_cancels_the_reminder_at_send_time(client, workspace, channel):
    state, link = prepare(client, workspace, channel)
    finish(state)
    reminder = Delivery.objects.for_workspace(workspace).order_by("-created_at").first()
    reminder.available_at = timezone.now()
    reminder.save()
    assert APIClient().get(f"/r/{link.code}/").status_code == 302
    adapter = Mock()
    with (
        patch("apps.channels.tasks.adapter_for", return_value=adapter),
        patch("apps.channels.tasks.rate_limit_wait", return_value=0),
    ):
        send_delivery(str(workspace.pk), str(reminder.pk))
    adapter.send_message.assert_not_called()
    reminder.refresh_from_db()
    assert reminder.status == "failed" and reminder.error_code == "link_already_clicked"


def test_old_run_clicks_do_not_cancel_a_new_run_reminder(client, workspace, channel):
    state, previous = prepare(client, workspace, channel)
    finish(state)
    state.cooldown_until = timezone.now() - timedelta(seconds=1)
    state.save()
    inbound(channel, "guide")
    state.refresh_from_db()
    assert state.run_token != previous.run_token
    step(str(workspace.pk), str(state.pk))
    step(str(workspace.pk), str(state.pk))
    APIClient().get(f"/r/{previous.code}/")
    state.refresh_from_db()
    assert finish(state).status == "completed"
    assert Delivery.objects.for_workspace(workspace).count() == 4


def test_reminder_cannot_reference_a_resource_on_only_one_branch(client, workspace, channel):
    graph = flow({"kind": "send_reminder", "text": "Reminder", "source_node": "resources"})
    graph["nodes"][0]["data"]["track_clicks"] = True
    graph["nodes"].insert(0, {"id": "split", "data": {"kind": "randomizer", "percentage": 50}})
    graph["start"] = "split"
    graph["edges"] += [
        {"source": "split", "target": "resources", "sourceHandle": "true"},
        {"source": "split", "target": "action-0", "sourceHandle": "false"},
    ]
    assert publish(client, workspace, graph).status_code == 400
