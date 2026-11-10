import pytest

from apps.content.models import BioPage
from apps.tenants.models import Membership, User

pytestmark = pytest.mark.django_db


def test_progress_reflects_workspace_data(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/setup-progress/"
    body = client.get(url).json()
    assert body["completed"] == 0
    assert {step["id"] for step in body["steps"]} >= {
        "connect_channel",
        "publish_bio",
        "invite_team",
    }

    BioPage.objects.for_workspace(workspace).create(
        workspace=workspace, slug="acme", title="Acme", published=True
    )
    mate = User.objects.create_user(username="m", email="m@x.com", password="A-long-password-42")
    Membership.objects.for_workspace(workspace).create(workspace=workspace, user=mate, role="agent")
    done = {step["id"] for step in client.get(url).json()["steps"] if step["done"]}
    assert done == {"publish_bio", "invite_team"}
