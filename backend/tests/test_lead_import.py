import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.crm.models import Lead
from tests.conftest import set_limits

pytestmark = pytest.mark.django_db


def upload(client, workspace, text, **extra):
    return client.post(
        f"/api/workspaces/{workspace.pk}/leads/import/",
        {
            "file": SimpleUploadedFile("contacts.csv", text.encode(), content_type="text/csv"),
            **extra,
        },
        format="multipart",
    )


CSV = (
    "First Name,Last Name,Email,Phone,Tags,Stage,Company\n"
    "Ada,Lovelace,ADA@example.com,+44 123,vip; newsletter,qualified,Analytical\n"
    "Grace,Hopper,grace@example.com,,,,Navy\n"
    ",,,,,,\n"
    "Bad,Email,not-an-email,,,,\n"
    "Odd,Stage,odd@example.com,,,maybe,\n"
)


def test_import_maps_columns_and_reports_bad_rows(client, workspace):
    res = upload(client, workspace, CSV, tag="imported")
    assert res.status_code == 200, res.content
    body = res.json()
    assert (body["created"], body["updated"], body["skipped"]) == (2, 0, 2)
    assert [e["reason"] for e in body["errors"]] == ["invalid email", "unknown stage"]
    ada = Lead.objects.for_workspace(workspace).get(email="ada@example.com")
    assert ada.name == "Ada Lovelace" and ada.stage == "qualified"
    assert ada.tags == ["vip", "newsletter", "imported"]
    assert ada.fields == {"phone": "+44 123", "company": "Analytical"}


def test_reimport_updates_by_email_without_duplicates(client, workspace):
    upload(client, workspace, CSV)
    again = upload(
        client, workspace, "email,tags,city\nada@example.com,speaker,London\ngrace@example.com,,\n"
    )
    assert again.json() == {"created": 0, "updated": 1, "unchanged": 1, "skipped": 0, "errors": []}
    ada = Lead.objects.for_workspace(workspace).get(email="ada@example.com")
    assert ada.name == "Ada Lovelace"  # blanks never overwrite
    assert "speaker" in ada.tags and ada.fields["city"] == "London"
    assert Lead.objects.for_workspace(workspace).count() == 2


def test_semicolon_files_and_contact_limit(client, workspace):
    set_limits(workspace, max_contacts=1)
    res = upload(client, workspace, "name;email\nA;a@example.com\nB;b@example.com\n")
    assert res.status_code == 402
    assert not Lead.objects.for_workspace(workspace).exists()
    set_limits(workspace, max_contacts=None)
    assert upload(client, workspace, "name;email\nA;a@example.com\n").json()["created"] == 1


@pytest.mark.parametrize(
    "text",
    ["", "\n\n", "colour,size\nred,big\n"],
)
def test_rejects_files_without_usable_columns(client, workspace, text):
    assert upload(client, workspace, text).status_code == 400


def test_agents_cannot_import(workspace):
    from rest_framework.test import APIClient

    from apps.tenants.models import Membership, User

    agent = User.objects.create_user(
        username="agent", email="a@x.com", password="A-long-password-42"
    )
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=agent, role="agent"
    )
    client = APIClient()
    client.force_authenticate(agent)
    assert upload(client, workspace, "name\nA\n").status_code == 403
