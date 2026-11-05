import pytest
from rest_framework.test import APIClient

from apps.crm.models import ChannelIdentity, Lead
from apps.tenants.models import Membership, User
from tests.test_meta_client import connect, inbound

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent(workspace):
    user = User.objects.create_user(username="contact-agent", email="agent@example.com")
    Membership.objects.for_workspace(workspace).create(workspace=workspace, user=user, role="agent")
    return user


def signed_in(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_manual_contact_assignment_persists_and_agent_can_manage_it(client, workspace, agent):
    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="Test")
    url = f"/api/workspaces/{workspace.pk}/leads/{lead.pk}/"
    agent_client = signed_in(agent)
    assert agent_client.get(url).status_code == 404
    response = client.patch(url, {"assigned_to": agent.pk}, format="json")
    assert response.status_code == 200, response.content
    assert response.json()["assigned_to"] == agent.pk
    assert response.json()["conversation_id"] is None
    lead.refresh_from_db()
    assert lead.assigned_to_id == agent.pk
    assert agent_client.get(url).status_code == 200
    assert agent_client.patch(url, {"stage": "qualified"}, format="json").status_code == 200
    assert str(lead.pk) in [
        row["id"]
        for row in agent_client.get(f"/api/workspaces/{workspace.pk}/leads/").json()["results"]
    ]
    assert client.patch(url, {"assigned_to": None}, format="json").status_code == 200
    assert agent_client.get(url).status_code == 404


def test_assignment_rejects_nonmembers_and_inactive_users(client, workspace, agent):
    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="Test")
    outsider = User.objects.create_user(username="outsider", email="outsider@example.com")
    url = f"/api/workspaces/{workspace.pk}/leads/{lead.pk}/"
    assert client.patch(url, {"assigned_to": outsider.pk}, format="json").status_code == 400
    agent.is_active = False
    agent.save()
    assert client.patch(url, {"assigned_to": agent.pk}, format="json").status_code == 400
    assert client.patch(url, {"assigned_to": "bad"}, format="json").status_code == 400
    lead.refresh_from_db()
    assert lead.assigned_to_id is None


def test_agent_cannot_reassign_contact(client, workspace, agent, user):
    lead = Lead.objects.for_workspace(workspace).create(
        workspace=workspace, name="Test", assigned_to=agent
    )
    url = f"/api/workspaces/{workspace.pk}/leads/{lead.pk}/"
    for target in [user.pk, agent.pk, None]:
        assert (
            signed_in(agent).patch(url, {"assigned_to": target}, format="json").status_code == 403
        )
    lead.refresh_from_db()
    assert lead.assigned_to_id == agent.pk


def test_contact_assignment_updates_linked_conversation(client, workspace, agent):
    conversation = inbound(connect(workspace), "Hi").conversation
    url = f"/api/workspaces/{workspace.pk}/leads/{conversation.identity.lead_id}/"
    response = client.patch(url, {"assigned_to": agent.pk}, format="json")
    assert response.status_code == 200, response.content
    conversation.refresh_from_db()
    assert conversation.assigned_to_id == agent.pk
    assert client.patch(url, {"assigned_to": None}, format="json").json()["assigned_to"] is None
    conversation.refresh_from_db()
    assert conversation.assigned_to_id is None


def test_new_conversation_inherits_contact_assignment(workspace, agent):
    channel = connect(workspace)
    lead = Lead.objects.for_workspace(workspace).create(
        workspace=workspace, name="Test", assigned_to=agent
    )
    ChannelIdentity.objects.for_workspace(workspace).create(
        workspace=workspace, lead=lead, connection=channel, external_id="assigned-sender"
    )
    conversation = inbound(channel, "Hello", sender="assigned-sender").conversation
    assert conversation.assigned_to_id == agent.pk


def test_removing_teammate_unassigns_manual_contacts(client, workspace, agent):
    lead = Lead.objects.for_workspace(workspace).create(
        workspace=workspace, name="Test", assigned_to=agent
    )
    member = Membership.objects.for_workspace(workspace).get(user=agent)
    assert client.delete(f"/api/workspaces/{workspace.pk}/members/{member.pk}/").status_code == 204
    lead.refresh_from_db()
    assert lead.assigned_to_id is None
