import pytest
from rest_framework.test import APIClient

from apps.channels.models import ChannelConnection
from apps.crm.models import Conversation, Lead, Message
from apps.tenants.models import Membership, User
from tests.test_meta_client import connect, inbound

pytestmark = pytest.mark.django_db


def test_owner_can_remove_disconnected_channel_and_history_but_keep_contact(client, workspace):
    channel = connect(workspace)
    message = inbound(channel, "Test message")
    lead_id = message.conversation.identity.lead_id
    assert (
        client.post(f"/api/workspaces/{workspace.pk}/channels/{channel.pk}/disconnect/").status_code
        == 200
    )
    response = client.delete(
        f"/api/workspaces/{workspace.pk}/channels/{channel.pk}/",
        {"confirm_delete": True},
        format="json",
    )
    assert response.status_code == 204, response.content
    assert not ChannelConnection.objects.for_workspace(workspace).filter(pk=channel.pk).exists()
    assert not Conversation.objects.for_workspace(workspace).exists()
    assert not Message.objects.for_workspace(workspace).exists()
    assert Lead.objects.for_workspace(workspace).filter(pk=lead_id).exists()


def test_active_channel_cannot_be_removed(client, workspace):
    channel = connect(workspace)
    response = client.delete(
        f"/api/workspaces/{workspace.pk}/channels/{channel.pk}/",
        {"confirm_delete": True},
        format="json",
    )
    assert response.status_code == 400
    assert ChannelConnection.objects.for_workspace(workspace).filter(pk=channel.pk).exists()


def test_removal_requires_explicit_confirmation(client, workspace):
    channel = connect(workspace)
    channel.status = "disconnected"
    channel.save()
    response = client.delete(f"/api/workspaces/{workspace.pk}/channels/{channel.pk}/")
    assert response.status_code == 400
    assert ChannelConnection.objects.for_workspace(workspace).filter(pk=channel.pk).exists()


@pytest.mark.parametrize("role", ["admin", "agent"])
def test_only_owner_can_remove_channel(workspace, role):
    channel = connect(workspace)
    channel.status = "disconnected"
    channel.save()
    user = User.objects.create_user(username=f"remove-{role}", email=f"{role}@example.com")
    Membership.objects.for_workspace(workspace).create(workspace=workspace, user=user, role=role)
    client = APIClient()
    client.force_authenticate(user)
    assert (
        client.delete(
            f"/api/workspaces/{workspace.pk}/channels/{channel.pk}/",
            {"confirm_delete": True},
            format="json",
        ).status_code
        == 403
    )
