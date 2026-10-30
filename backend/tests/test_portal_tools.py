import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from rest_framework.test import APIClient

from apps.crm.models import Lead
from apps.tools.models import FormSubmission, LinkClickDay

pytestmark = pytest.mark.django_db

FIELDS = [
    {"id": "name", "label": "Your name", "type": "text", "required": True},
    {"id": "email", "label": "Email", "type": "email", "required": True},
]


def create_form(client, workspace, **extra):
    response = client.post(
        f"/api/workspaces/{workspace.pk}/forms/",
        {"title": "Enquiry", "slug": "enquiry", "fields": FIELDS, "published": True, **extra},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def test_form_captures_encrypted_answers_once_without_reopening_opt_out(client, workspace):
    form = create_form(client, workspace)
    lead = Lead.objects.for_workspace(workspace).create(
        workspace=workspace, email="person@example.com", opted_out=True
    )
    anonymous = APIClient()
    url = "/api/public/forms/enquiry/"
    assert anonymous.get(url).json()["fields"] == FIELDS
    body = {
        "request_id": str(uuid.uuid4()),
        "consent": True,
        "answers": {"name": "Person", "email": "person@example.com"},
    }
    assert anonymous.post(url, {**body, "consent": False}, format="json").status_code == 400
    assert anonymous.post(url, {**body, "website": "bot"}, format="json").status_code == 400
    for _ in range(2):
        assert anonymous.post(url, body, format="json").status_code in {200, 201}
    assert FormSubmission.objects.for_workspace(workspace).count() == 1
    assert Lead.objects.for_workspace(workspace).count() == 1
    lead.refresh_from_db()
    assert lead.opted_out
    response = client.get(f"/api/workspaces/{workspace.pk}/forms/{form['id']}/submissions/")
    assert response.json()[0]["answers"] == body["answers"]
    assert (
        anonymous.get(f"/api/workspaces/{workspace.pk}/forms/{form['id']}/submissions/").status_code
        == 403
    )
    unpublished = client.patch(
        f"/api/workspaces/{workspace.pk}/forms/{form['id']}/",
        {"published": False},
        format="json",
    )
    assert unpublished.status_code == 200
    assert unpublished.json()["submissions"] == 1
    detail_url = f"/api/workspaces/{workspace.pk}/forms/{form['id']}/"
    assert client.get(detail_url).json()["submissions"] == 1
    updated = client.patch(detail_url, {"title": "Updated enquiry"}, format="json")
    assert updated.json()["submissions"] == 1
    assert client.get(f"/api/workspaces/{workspace.pk}/forms/").json()[0]["submissions"] == 1
    assert anonymous.post(url, body, format="json").status_code == 404


def test_form_rejects_unknown_fields_bad_email_and_missing_definition(client, workspace):
    create_form(client, workspace)
    anonymous = APIClient()
    for answers in [
        {"name": "P", "email": "bad"},
        {"name": "", "email": "p@example.com"},
        {"name": "P", "email": "p@example.com", "admin": "yes"},
    ]:
        assert (
            anonymous.post(
                "/api/public/forms/enquiry/",
                {"request_id": str(uuid.uuid4()), "consent": True, "answers": answers},
                format="json",
            ).status_code
            == 400
        )
    assert (
        client.post(
            f"/api/workspaces/{workspace.pk}/forms/",
            {"title": "Empty", "slug": "empty"},
            format="json",
        ).status_code
        == 400
    )
    assert not Lead.objects.for_workspace(workspace).exists()


def test_tracking_app_adds_campaign_tags_counts_daily_and_attributes_form(client, workspace):
    link = client.post(
        f"/api/workspaces/{workspace.pk}/deeplinks/",
        {
            "title": "Launch",
            "platform": "custom",
            "target": "https://example.com?keep=1&utm_source=old",
            "code": "launch",
            "campaign": "October",
            "source": "instagram",
            "medium": "dm",
        },
        format="json",
    ).json()
    anonymous = APIClient()
    assert anonymous.head("/go/launch/").status_code == 302
    assert not LinkClickDay.objects.for_workspace(workspace).exists()
    redirect = anonymous.get("/go/launch/")
    assert parse_qs(urlsplit(redirect["Location"]).query) == {
        "keep": ["1"],
        "utm_source": ["instagram"],
        "utm_medium": ["dm"],
        "utm_campaign": ["October"],
    }
    create_form(client, workspace)
    assert (
        anonymous.post(
            "/api/public/forms/enquiry/",
            {
                "request_id": str(uuid.uuid4()),
                "consent": True,
                "ref": "launch",
                "answers": {"name": "P", "email": "p@example.com"},
            },
            format="json",
        ).status_code
        == 201
    )
    stats = client.get(f"/api/workspaces/{workspace.pk}/deeplinks/{link['id']}/stats/").json()
    assert stats["clicks"] == stats["form_submissions"] == stats["daily"][0]["clicks"] == 1
    assert Lead.objects.for_workspace(workspace).get().fields["campaign"] == "October"


def test_creator_publication_validates_links_and_preserves_private_draft(client, workspace):
    url = f"/api/workspaces/{workspace.pk}/creator-kit/"
    body = {
        "slug": "creator",
        "name": "Creator",
        "published": False,
        "statistics": [{"label": "Followers", "value": "12,000"}],
        "services": [{"title": "Video", "description": "Sponsored short video"}],
        "links": [{"label": "Portfolio", "url": "https://example.com"}],
    }
    assert client.put(url, body, format="json").status_code == 200
    anonymous = APIClient()
    assert anonymous.get("/api/public/creator/creator/").status_code == 404
    assert (
        client.put(
            url,
            {**body, "links": [{"label": "Unsafe", "url": "javascript:alert(1)"}]},
            format="json",
        ).status_code
        == 400
    )
    assert client.put(url, {**body, "published": True}, format="json").status_code == 200
    assert anonymous.get("/api/public/creator/creator/").json()["statistics"] == body["statistics"]
