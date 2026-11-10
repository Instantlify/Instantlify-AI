from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.channels.models import ChannelConnection, WebhookEvent
from apps.crm.models import Lead
from apps.crm.services import receive
from apps.tenants.models import Membership, User
from tests.conftest import set_limits

pytestmark = pytest.mark.django_db


def account(workspace, name):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider="instagram",
        external_account_id=name,
        display_name=name,
        access_token="t",
        expires_at=timezone.now() + timedelta(days=30),
        status="active",
        is_test=True,
    )


def message(channel, sender):
    event = WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id=f"e-{sender}",
        payload="{}",
        available_at=timezone.now(),
    )
    return receive(event, {"sender_id": sender, "text": "hi", "kind": "dm"})


@pytest.fixture
def teammate(workspace):
    set_limits(workspace, team_seats=10)
    user = User.objects.create_user(
        username="ann", email="ann@x.com", password="A-long-password-42"
    )
    membership = Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=user, role="admin"
    )
    client = APIClient()
    client.force_authenticate(user)
    return client, membership


def limit(owner, workspace, membership, **fields):
    res = owner.patch(
        f"/api/workspaces/{workspace.pk}/members/{membership.pk}/", fields, format="json"
    )
    assert res.status_code == 200, res.content
    return res.json()


def test_account_limits_filter_conversations_contacts_and_accounts(client, workspace, teammate):
    mate, membership = teammate
    shop, support = account(workspace, "shop"), account(workspace, "support")
    message(shop, "buyer")
    message(support, "helpme")
    base = f"/api/workspaces/{workspace.pk}"
    assert mate.get(f"{base}/conversations/").json()["count"] == 2

    limit(client, workspace, membership, allowed_connections=[str(support.pk)])
    rows = mate.get(f"{base}/conversations/").json()["results"]
    assert [row["connection_id"] for row in rows] == [str(support.pk)]
    names = {lead["id"] for lead in mate.get(f"{base}/leads/").json()["results"]}
    assert names == {
        str(Lead.objects.for_workspace(workspace).get(channelidentity__connection=support).pk)
    }
    accounts = mate.get(f"{base}/connections/").json()["results"]
    assert [item["id"] for item in accounts] == [str(support.pk)]
    # The owner is never limited.
    assert client.get(f"{base}/conversations/").json()["count"] == 2


def test_section_limits_are_enforced_on_the_api(client, workspace, teammate):
    mate, membership = teammate
    base = f"/api/workspaces/{workspace.pk}"
    limit(client, workspace, membership, allowed_sections=["inbox"])
    assert mate.get(f"{base}/conversations/").status_code == 200
    assert mate.get(f"{base}/leads/").status_code == 200  # the inbox contact panel needs it
    assert mate.get(f"{base}/pipeline-stages/").status_code == 200  # shared lookup
    for path in ("automations/", "bio/", "forms/", "analytics/funnel/", "agent/"):
        res = mate.get(f"{base}/{path}")
        assert res.status_code == 403, path
    workspaces = {item["id"]: item for item in mate.get("/api/workspaces/").json()["results"]}
    assert workspaces[str(workspace.pk)]["allowed_sections"] == ["inbox"]

    limit(client, workspace, membership, allowed_sections=[])
    assert mate.get(f"{base}/automations/").status_code == 200


def test_limits_are_validated_and_owner_only(client, workspace, teammate):
    mate, membership = teammate
    url = f"/api/workspaces/{workspace.pk}/members/{membership.pk}/"
    assert client.patch(url, {"allowed_sections": ["nope"]}, format="json").status_code == 400
    assert (
        client.patch(
            url,
            {"allowed_connections": ["00000000-0000-0000-0000-000000000000"]},
            format="json",
        ).status_code
        == 400
    )
    assert mate.patch(url, {"allowed_sections": []}, format="json").status_code == 403
