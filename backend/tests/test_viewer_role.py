# ruff: noqa: F811 -- pytest fixtures imported from the runtime tests
import pytest
from rest_framework.test import APIClient

from apps.crm.models import Conversation, Lead
from apps.tenants.models import Membership, User
from tests.test_automation_runtime import channel, inbound, quiet_notify  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def viewer(workspace):
    user = User.objects.create_user(
        username="vic", email="vic@x.com", password="A-long-password-42"
    )
    membership = Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=user, role="viewer"
    )
    client = APIClient()
    client.force_authenticate(user)
    return client, membership


def test_viewer_reads_everything_but_writes_nothing(workspace, channel, viewer):
    client, _ = viewer
    inbound(channel, "hello")
    conversation = Conversation.objects.for_workspace(workspace).get()
    lead = Lead.objects.for_workspace(workspace).get()
    base = f"/api/workspaces/{workspace.pk}"

    assert client.get(f"{base}/conversations/").json()["count"] == 1
    assert client.get(f"{base}/leads/").status_code == 200
    assert client.get(f"{base}/conversations/{conversation.pk}/messages/").status_code == 200

    refused = [
        client.patch(f"{base}/leads/{lead.pk}/", {"name": "X"}, format="json"),
        client.post(
            f"{base}/conversations/{conversation.pk}/messages/",
            {"text": "hi"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="k",
        ),
        client.post(f"{base}/conversations/{conversation.pk}/notes/", {"text": "n"}, format="json"),
        client.put(f"{base}/saved-replies/", {"replies": ["x"]}, format="json"),
        client.post(f"{base}/leads/", {"name": "New"}, format="json"),
    ]
    assert [res.status_code for res in refused] == [403, 403, 403, 403, 403]
    assert "read-only" in refused[0].json()["detail"]
    lead.refresh_from_db()
    assert lead.name != "X"

    # Marking a thread read is allowed: it changes nothing anyone else relies on.
    assert client.post(f"{base}/conversations/{conversation.pk}/read/").status_code == 204


def test_viewer_can_leave_but_not_remove_others(workspace, viewer, user):
    client, membership = viewer
    owner_membership = Membership.objects.for_workspace(workspace).get(user=user)
    base = f"/api/workspaces/{workspace.pk}/members"
    assert client.delete(f"{base}/{owner_membership.pk}/").status_code == 403
    assert client.delete(f"{base}/{membership.pk}/").status_code in {200, 204}
    assert not Membership.objects.for_workspace(workspace).filter(pk=membership.pk).exists()


def test_owner_can_invite_and_assign_viewers(client, workspace, viewer):
    from tests.conftest import set_limits

    set_limits(workspace, team_seats=10)
    _, membership = viewer
    res = client.post(
        f"/api/workspaces/{workspace.pk}/invitations/",
        {"email": "new@x.com", "role": "viewer"},
        format="json",
    )
    assert res.status_code in {200, 201}, res.content
    change = client.patch(
        f"/api/workspaces/{workspace.pk}/members/{membership.pk}/", {"role": "agent"}, format="json"
    )
    assert change.status_code == 200 and change.json()["role"] == "agent"
