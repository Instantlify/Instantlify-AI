import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.crm.models import Lead
from apps.crm.stages import DEFAULT_STAGES

pytestmark = pytest.mark.django_db


def url(workspace):
    return f"/api/workspaces/{workspace.pk}/pipeline-stages/"


def custom(*extra):
    return [*DEFAULT_STAGES, *extra]


def test_defaults_then_custom_stages_are_usable_everywhere(client, workspace):
    assert [s["id"] for s in client.get(url(workspace)).json()["stages"]] == [
        s["id"] for s in DEFAULT_STAGES
    ]
    stages = custom({"id": "demo", "label": "Demo booked", "color": "#AA00FF"})
    res = client.put(url(workspace), {"stages": stages}, format="json")
    assert res.status_code == 200, res.content
    assert res.json()["stages"][-1] == {"id": "demo", "label": "Demo booked", "color": "#aa00ff"}

    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="A")
    leads = f"/api/workspaces/{workspace.pk}/leads/"
    assert client.patch(f"{leads}{lead.pk}/", {"stage": "demo"}, format="json").status_code == 200
    assert client.patch(f"{leads}{lead.pk}/", {"stage": "nope"}, format="json").status_code == 400
    bulk = client.post(
        f"{leads}bulk/", {"ids": [str(lead.pk)], "action": "stage", "value": "demo"}, format="json"
    )
    assert bulk.status_code == 200
    imported = client.post(
        f"{leads}import/",
        {"file": SimpleUploadedFile("c.csv", b"name,stage\nB,demo\n", content_type="text/csv")},
        format="multipart",
    )
    assert imported.json()["created"] == 1


def test_removing_a_stage_moves_its_contacts_to_new(client, workspace):
    client.put(
        url(workspace),
        {"stages": custom({"id": "demo", "label": "Demo", "color": "#123456"})},
        format="json",
    )
    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="A", stage="demo")
    res = client.put(url(workspace), {"stages": DEFAULT_STAGES}, format="json")
    assert res.json()["moved_contacts"] == 1
    lead.refresh_from_db()
    assert lead.stage == "new"


@pytest.mark.parametrize(
    "stages",
    [
        [s for s in DEFAULT_STAGES if s["id"] != "won"],
        custom({"id": "Bad Id", "label": "x", "color": "#123456"}),
        custom({"id": "qualified", "label": "dup", "color": "#123456"}),
        custom({"id": "x", "label": "", "color": "#123456"}),
        custom({"id": "x", "label": "X", "color": "red"}),
        custom(*({"id": f"s{i}", "label": "S", "color": "#123456"} for i in range(15))),
    ],
)
def test_invalid_stage_lists(client, workspace, stages):
    assert client.put(url(workspace), {"stages": stages}, format="json").status_code == 400


def test_agents_cannot_edit_stages(workspace):
    from rest_framework.test import APIClient

    from apps.tenants.models import Membership, User

    agent = User.objects.create_user(username="ag", email="ag@x.com", password="A-long-password-42")
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=agent, role="agent"
    )
    client = APIClient()
    client.force_authenticate(agent)
    assert client.get(url(workspace)).status_code == 200
    assert client.put(url(workspace), {"stages": DEFAULT_STAGES}, format="json").status_code == 403


def test_flows_can_only_set_existing_stages(client, workspace):
    flow = {
        "start": "s",
        "triggers": [{"kind": "dm", "keyword": "hi"}],
        "nodes": [
            {"id": "s", "data": {"kind": "set_stage", "stage": "demo"}},
            {"id": "e", "data": {"kind": "end"}},
        ],
        "edges": [{"source": "s", "target": "e"}],
    }
    created = client.post(
        f"/api/workspaces/{workspace.pk}/automations/", {"name": "x", "draft": flow}, format="json"
    ).json()
    publish = f"/api/workspaces/{workspace.pk}/automations/{created['id']}/publish/"
    assert client.post(publish, {"graph": flow}, format="json").status_code == 400
    client.put(
        url(workspace),
        {"stages": custom({"id": "demo", "label": "Demo", "color": "#123456"})},
        format="json",
    )
    assert client.post(publish, {"graph": flow}, format="json").status_code == 200
