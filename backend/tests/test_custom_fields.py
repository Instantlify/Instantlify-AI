import pytest

from apps.crm.models import Lead

pytestmark = pytest.mark.django_db

DEFS = [
    {"key": "budget", "label": "Budget", "type": "number"},
    {"key": "renewal", "label": "Renewal date", "type": "date"},
    {"key": "plan", "label": "Plan", "type": "select", "options": ["Starter", "Pro"]},
    {"key": "site", "label": "Website", "type": "url"},
    {"key": "billing_email", "label": "Billing email", "type": "email"},
    {"key": "notes", "label": "Notes", "type": "text"},
]


def defs_url(workspace):
    return f"/api/workspaces/{workspace.pk}/custom-fields/"


def lead_url(workspace, lead):
    return f"/api/workspaces/{workspace.pk}/leads/{lead.pk}/"


def test_definitions_round_trip_and_values_are_typed(client, workspace):
    assert client.get(defs_url(workspace)).json() == {"fields": []}
    assert client.put(defs_url(workspace), {"fields": DEFS}, format="json").status_code == 200
    assert client.get(defs_url(workspace)).json()["fields"] == DEFS

    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="A")
    ok = client.patch(
        lead_url(workspace, lead),
        {
            "fields": {
                "budget": " 1500.0 ",
                "renewal": "2027-01-31",
                "plan": "pro",
                "site": "https://example.com",
                "billing_email": "Billing@Example.com",
                "city": "Lahore",
            }
        },
        format="json",
    )
    assert ok.status_code == 200, ok.content
    lead.refresh_from_db()
    assert lead.fields == {
        "budget": "1500",
        "renewal": "2027-01-31",
        "plan": "Pro",
        "site": "https://example.com",
        "billing_email": "billing@example.com",
        "city": "Lahore",  # undefined keys stay free-form
    }


@pytest.mark.parametrize(
    "fields",
    [
        {"budget": "lots"},
        {"renewal": "31/01/2027"},
        {"plan": "Enterprise"},
        {"site": "not a url"},
        {"billing_email": "nope"},
    ],
)
def test_invalid_values_are_rejected(client, workspace, fields):
    client.put(defs_url(workspace), {"fields": DEFS}, format="json")
    lead = Lead.objects.for_workspace(workspace).create(workspace=workspace, name="A")
    assert (
        client.patch(lead_url(workspace, lead), {"fields": fields}, format="json").status_code
        == 400
    )


@pytest.mark.parametrize(
    "fields",
    [
        [{"key": "Bad Key", "label": "x", "type": "text"}],
        [{"key": "a", "label": "x", "type": "text"}, {"key": "a", "label": "y", "type": "text"}],
        [{"key": "a", "label": "", "type": "text"}],
        [{"key": "a", "label": "A", "type": "color"}],
        [{"key": "a", "label": "A", "type": "select", "options": []}],
        [{"key": "source", "label": "Source", "type": "text"}],
        [{"key": f"f{i}", "label": "F", "type": "text"} for i in range(31)],
    ],
)
def test_invalid_definitions(client, workspace, fields):
    assert client.put(defs_url(workspace), {"fields": fields}, format="json").status_code == 400


def test_agents_can_read_but_not_edit_definitions(workspace):
    from rest_framework.test import APIClient

    from apps.tenants.models import Membership, User

    agent = User.objects.create_user(username="ag", email="ag@x.com", password="A-long-password-42")
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=agent, role="agent"
    )
    client = APIClient()
    client.force_authenticate(agent)
    assert client.get(defs_url(workspace)).status_code == 200
    assert client.put(defs_url(workspace), {"fields": DEFS}, format="json").status_code == 403
