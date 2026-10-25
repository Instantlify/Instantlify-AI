from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.channels.models import Delivery
from apps.channels.tasks import send_delivery
from apps.crm.campaigns import process_campaign
from apps.crm.models import Campaign, CampaignRecipient
from tests.test_meta_client import connect, inbound

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def quiet_campaign_notifications():
    with (
        patch("apps.crm.services.notify"),
        patch("apps.channels.tasks.rate_limit_wait", return_value=0),
    ):
        yield


def create(client, workspace, connection, **extra):
    response = client.post(
        f"/api/workspaces/{workspace.pk}/campaigns/",
        {
            "name": "Launch",
            "connection_id": str(connection.pk),
            "text": "Hello {{name}}",
            "tag": "campaign-received",
            "audience": {"mode": "all"},
            **extra,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def launch(client, workspace, campaign):
    return client.post(
        f"/api/workspaces/{workspace.pk}/campaigns/{campaign['id']}/launch/", {}, format="json"
    )


def test_campaign_freezes_eligible_account_audience_and_delivers_once(client, workspace):
    channel = connect(workspace)
    eligible = inbound(channel, "Hello", sender="private").conversation
    inbound(channel, "Comment", kind="comment", sender="public", comment_id="comment-one")
    opted = inbound(channel, "Hello", sender="opted").conversation.identity.lead
    opted.opted_out = True
    opted.save()
    inbound(connect(workspace, "whatsapp", "another-account"), "Hi", sender="another")
    campaign = create(
        client,
        workspace,
        channel,
        buttons=[{"type": "web_url", "title": "Offer", "url": "https://example.com/offer"}],
        media_url="https://example.com/photo.jpg",
        media_type="image",
    )
    prefix = f"/api/workspaces/{workspace.pk}/campaigns/"
    preview = client.post(prefix + "audience/", campaign, format="json")
    assert preview.status_code == 200, preview.content
    assert preview.json()["eligible"] == 1
    assert launch(client, workspace, campaign).status_code == 202
    assert launch(client, workspace, campaign).status_code == 200
    assert CampaignRecipient.objects.for_workspace(workspace).count() == 1
    assert (
        client.patch(
            prefix + campaign["id"] + "/", {"text": "Changed after launch"}, format="json"
        ).status_code
        == 400
    )
    process_campaign(str(workspace.pk), campaign["id"])
    process_campaign(str(workspace.pk), campaign["id"])
    assert Delivery.objects.for_workspace(workspace).count() == 2
    Delivery.objects.for_workspace(workspace).update(available_at=timezone.now())
    for delivery in Delivery.objects.for_workspace(workspace):
        send_delivery(str(workspace.pk), str(delivery.pk))
    process_campaign(str(workspace.pk), campaign["id"])
    saved = Campaign.objects.for_workspace(workspace).get()
    assert saved.status == "completed"
    assert CampaignRecipient.objects.for_workspace(workspace).get().status == "sent"
    eligible.identity.lead.refresh_from_db()
    assert "campaign-received" in eligible.identity.lead.tags
    assert client.get(prefix + campaign["id"] + "/").json()["counts"] == {"sent": 1}


def test_opt_out_or_window_expiry_after_launch_is_skipped_at_dispatch(client, workspace):
    channel = connect(workspace)
    thread = inbound(channel, "Hi").conversation
    campaign = create(client, workspace, channel)
    assert launch(client, workspace, campaign).status_code == 202
    thread.last_inbound_at = timezone.now() - timedelta(hours=25)
    thread.save()
    process_campaign(str(workspace.pk), campaign["id"])
    assert not Delivery.objects.for_workspace(workspace).exists()
    assert CampaignRecipient.objects.for_workspace(workspace).get().status == "skipped"


def test_scheduled_campaign_can_be_cancelled_without_queueing_messages(client, workspace):
    channel = connect(workspace)
    inbound(channel, "Hi")
    campaign = create(
        client, workspace, channel, scheduled_at=(timezone.now() + timedelta(hours=1)).isoformat()
    )
    assert launch(client, workspace, campaign).status_code == 202
    process_campaign(str(workspace.pk), campaign["id"])
    assert not Delivery.objects.for_workspace(workspace).exists()
    response = client.post(
        f"/api/workspaces/{workspace.pk}/campaigns/{campaign['id']}/cancel/", {}, format="json"
    )
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    assert CampaignRecipient.objects.for_workspace(workspace).get().status == "cancelled"
    process_campaign(str(workspace.pk), campaign["id"])
    assert not Delivery.objects.for_workspace(workspace).exists()


def test_empty_selection_cannot_expand_to_everyone_and_foreign_account_is_rejected(
    client, workspace, user
):
    from apps.tenants.services import create_workspace

    channel = connect(workspace)
    url = f"/api/workspaces/{workspace.pk}/campaigns/"
    response = client.post(
        url,
        {
            "name": "Empty selection",
            "connection_id": str(channel.pk),
            "audience": {"mode": "selected", "lead_ids": []},
        },
        format="json",
    )
    assert response.status_code == 400
    other = create_workspace(user, "Other")
    foreign = connect(other, account="foreign-account")
    assert (
        client.post(
            url, {"name": "Wrong account", "connection_id": str(foreign.pk)}, format="json"
        ).status_code
        == 400
    )


def test_saved_draft_and_filtered_audience_do_not_send_anything(client, workspace):
    channel = connect(workspace)
    first = inbound(channel, "Hello", sender="first").conversation.identity.lead
    first.tags = ["vip"]
    first.stage = "qualified"
    first.save()
    inbound(channel, "Hello", sender="second")
    campaign = create(
        client,
        workspace,
        channel,
        audience={"mode": "filtered", "tags": ["vip"], "stages": ["qualified"]},
    )
    assert campaign["status"] == "draft"
    assert not Delivery.objects.for_workspace(workspace).exists()
    preview = client.post(
        f"/api/workspaces/{workspace.pk}/campaigns/audience/", campaign, format="json"
    )
    assert preview.json()["eligible"] == 1
