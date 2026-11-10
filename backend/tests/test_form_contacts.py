import json
import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.crm.models import Lead
from apps.tools.models import FormSubmission
from tests.test_portal_tools import create_form

pytestmark = pytest.mark.django_db


def submit(answers):
    return APIClient().post(
        "/api/public/forms/enquiry/",
        {"request_id": str(uuid.uuid4()), "consent": True, "answers": answers},
        format="json",
    )


def test_grouped_contact_maps_to_crm_without_reopening_opt_out(client, workspace):
    fields = [
        {
            "id": "contact",
            "label": "Contact details",
            "type": "contact_block",
            "required": True,
            "include_phone": True,
        }
    ]
    create_form(client, workspace, fields=fields)
    lead = Lead.objects.for_workspace(workspace).create(
        workspace=workspace, email="p@example.com", opted_out=True, fields={"existing": "kept"}
    )
    contact = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "P@example.com",
        "phone": "12345",
    }
    assert submit({"contact": contact}).status_code == 201
    lead.refresh_from_db()
    assert lead.name == "Ada Lovelace" and lead.opted_out
    assert lead.fields["phone"] == "12345" and lead.fields["existing"] == "kept"
    assert (
        json.loads(FormSubmission.objects.for_workspace(workspace).get().answers)["contact"]
        == contact
    )


def test_optional_crm_capture_allows_contactless_survey_and_never_creates_lead(client, workspace):
    create_form(
        client,
        workspace,
        capture_contacts=False,
        fields=[{"id": "feedback", "label": "Feedback", "type": "text", "required": True}],
    )
    with patch("apps.public_api.services.emit") as emit:
        assert submit({"feedback": "Useful"}).status_code == 201
    assert not Lead.objects.for_workspace(workspace).exists()
    assert FormSubmission.objects.for_workspace(workspace).get().lead_id is None
    assert emit.call_args.args[2]["lead_id"] is None


@pytest.mark.parametrize(
    "kind,url",
    [
        ("calendly", "https://calendly.com/team/chat"),
        ("calcom", "https://cal.com/team/chat"),
        ("tidycal", "https://tidycal.com/team/chat"),
    ],
)
def test_booking_embeds_are_not_claimed_as_booking_confirmations(client, workspace, kind, url):
    create_form(
        client,
        workspace,
        capture_contacts=False,
        fields=[
            {
                "id": "welcome",
                "label": "Welcome",
                "type": "cover_card",
                "description": "Tell us about yourself",
                "required": False,
            },
            {
                "id": "calendar",
                "label": "Book",
                "type": kind,
                "booking_url": url,
                "required": False,
            },
        ],
    )
    assert submit({"calendar": "forged booking confirmation"}).status_code == 201
    assert json.loads(FormSubmission.objects.for_workspace(workspace).get().answers) == {}


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://evil.example/calendly.com",
        "https://calendly.com.evil.example/book",
        "https://user:password@calendly.com/book",
    ],
)
def test_booking_embed_rejects_untrusted_hosts_and_credentials(client, workspace, url):
    response = client.post(
        f"/api/workspaces/{workspace.pk}/forms/",
        {
            "title": "Bad",
            "slug": "bad",
            "capture_contacts": False,
            "fields": [{"id": "calendar", "label": "Book", "type": "calendly", "booking_url": url}],
        },
        format="json",
    )
    assert response.status_code == 400
