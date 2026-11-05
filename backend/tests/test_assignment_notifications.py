import pytest
from rest_framework.test import APIClient

from apps.crm.models import AssignmentNotification, Lead
from apps.tenants.models import Membership, User
from tests.test_meta_client import connect, inbound

pytestmark = pytest.mark.django_db


@pytest.fixture
def teammate(workspace):
    user = User.objects.create_user(username="notified-agent", email="notify@example.com")
    Membership.objects.for_workspace(workspace).create(workspace=workspace, user=user, role="agent")
    client = APIClient()
    client.force_authenticate(user)
    return user, client


def test_assignment_persists_unread_notification_and_noop_does_not_duplicate(
    client, workspace, teammate
):
    agent, agent_client = teammate
    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="Test contact")
    url = f"/api/workspaces/{workspace.pk}/leads/{lead.pk}/"
    assert client.patch(url, {"assigned_to": agent.pk}, format="json").status_code == 200
    assert client.patch(url, {"assigned_to": agent.pk}, format="json").status_code == 200
    feed_url = f"/api/workspaces/{workspace.pk}/assignment-notifications/"
    feed = agent_client.get(feed_url).json()
    assert feed["unread_count"] == 1
    assert feed["results"][0]["contact_name"] == "Test contact"
    assert client.get(feed_url).json()["unread_count"] == 0
    notification = feed["results"][0]["id"]
    # The owner cannot mark the agent's notification read.
    client.patch(feed_url, {"id": notification}, format="json")
    assert agent_client.get(feed_url).json()["unread_count"] == 1
    assert agent_client.patch(feed_url, {"id": notification}, format="json").status_code == 200
    assert agent_client.get(feed_url).json()["unread_count"] == 0


def test_unassignment_removes_unread_alert_and_contact_access(client, workspace, teammate):
    agent, agent_client = teammate
    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="Test")
    url = f"/api/workspaces/{workspace.pk}/leads/{lead.pk}/"
    client.patch(url, {"assigned_to": agent.pk}, format="json")
    client.patch(url, {"assigned_to": None}, format="json")
    feed = agent_client.get(f"/api/workspaces/{workspace.pk}/assignment-notifications/").json()
    assert feed == {"unread_count": 0, "results": []}


def test_conversation_assignment_creates_notification(client, workspace, teammate):
    agent, agent_client = teammate
    conversation = inbound(connect(workspace), "Hello").conversation
    response = client.patch(
        f"/api/workspaces/{workspace.pk}/conversations/{conversation.pk}/",
        {"assigned_to": agent.pk},
        format="json",
    )
    assert response.status_code == 200
    assert (
        agent_client.get(f"/api/workspaces/{workspace.pk}/assignment-notifications/").json()[
            "unread_count"
        ]
        == 1
    )


def test_self_assignment_does_not_notify_self(client, user, workspace):
    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="Test")
    client.patch(
        f"/api/workspaces/{workspace.pk}/leads/{lead.pk}/", {"assigned_to": user.pk}, format="json"
    )
    assert not AssignmentNotification.objects.for_workspace(workspace).exists()


def test_notification_feed_requires_workspace_membership(client, workspace):
    outsider = User.objects.create_user(
        username="outside-notifications", email="outside@example.com"
    )
    other = APIClient()
    other.force_authenticate(outsider)
    url = f"/api/workspaces/{workspace.pk}/assignment-notifications/"
    assert other.get(url).status_code == 404
    assert other.patch(url, {"all_read": True}, format="json").status_code == 404
