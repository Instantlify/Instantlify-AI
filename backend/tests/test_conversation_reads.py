# ruff: noqa: F811 -- pytest fixtures imported from the runtime tests
import pytest
from rest_framework.test import APIClient

from apps.crm.models import Conversation
from apps.tenants.models import Membership, User
from tests.test_automation_runtime import channel, inbound, quiet_notify  # noqa: F401

pytestmark = pytest.mark.django_db


def listing(client, workspace):
    return client.get(f"/api/workspaces/{workspace.pk}/conversations/").json()["results"]


def test_unread_and_seen_by_per_teammate(client, workspace, channel):
    mate = User.objects.create_user(
        username="sam", email="sam@x.com", password="A-long-password-42", first_name="Sam"
    )
    Membership.objects.for_workspace(workspace).create(workspace=workspace, user=mate, role="admin")
    other = APIClient()
    other.force_authenticate(mate)

    inbound(channel, "hello")
    conversation = Conversation.objects.for_workspace(workspace).get()
    [row] = listing(client, workspace)
    assert row["unread"] is True and row["seen_by"] == []

    read = f"/api/workspaces/{workspace.pk}/conversations/{conversation.pk}/read/"
    assert client.post(read).status_code == 204
    assert listing(client, workspace)[0]["unread"] is False
    # Reading is per person: the teammate still has it unread, and now sees who read it.
    [theirs] = listing(other, workspace)
    assert theirs["unread"] is True and theirs["seen_by"] == ["owner"]

    other.post(read)
    assert listing(client, workspace)[0]["seen_by"] == ["Sam"]

    # A new customer message makes it unread again for everyone.
    inbound(channel, "are you there?")
    rows = listing(client, workspace)
    assert rows[0]["unread"] is True and rows[0]["seen_by"] == []


def test_cannot_mark_conversations_outside_the_workspace(client, workspace):
    import uuid

    url = f"/api/workspaces/{workspace.pk}/conversations/{uuid.uuid4()}/read/"
    assert client.post(url).status_code == 404
