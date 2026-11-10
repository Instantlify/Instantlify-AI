import base64
import json
import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.tools.models import FormSubmission
from tests.test_portal_tools import FIELDS, create_form

pytestmark = pytest.mark.django_db


def body(value):
    return {
        "request_id": str(uuid.uuid4()),
        "consent": True,
        "answers": {"name": "P", "email": "p@example.com", "attachment": value},
    }


def test_file_submission_stays_private_encrypted_and_download_is_tenant_scoped(client, workspace):
    form = create_form(
        client,
        workspace,
        fields=[
            *FIELDS,
            {"id": "attachment", "label": "Document", "type": "file_upload", "required": True},
        ],
    )
    value = {
        "name": "../private\r\n.txt",
        "data": base64.b64encode(b"Private answer content").decode(),
    }
    with patch("apps.public_api.services.emit") as emit:
        assert (
            APIClient().post("/api/public/forms/enquiry/", body(value), format="json").status_code
            == 201
        )
    assert "data" not in emit.call_args.args[2]["answers"]["attachment"]
    row = FormSubmission.objects.for_workspace(workspace).get()
    answer = json.loads(row.answers)["attachment"]
    assert answer["name"] == "private.txt" and answer["size"] == 22
    listing = client.get(f"/api/workspaces/{workspace.pk}/forms/{form['id']}/submissions/").json()
    metadata = listing[0]["answers"]["attachment"]
    assert "data" not in metadata and metadata["size"] == 22
    url = metadata["download_url"]
    response = client.get(url)
    assert response.status_code == 200 and response.content == b"Private answer content"
    assert response["Content-Disposition"].startswith("attachment;")
    assert set(response["Cache-Control"].split(", ")) == {"private", "no-store"}
    assert APIClient().get(url).status_code == 403
    from apps.tenants.models import User
    from apps.tenants.services import create_workspace

    stranger = User.objects.create_user(
        username="stranger", email="stranger@example.com", password="example-password"
    )
    other = create_workspace(stranger, "Other")
    client.force_authenticate(stranger)
    assert client.get(url).status_code in {403, 404}
    assert client.get(url.replace(str(workspace.pk), str(other.pk))).status_code == 404


@pytest.mark.parametrize(
    "value",
    [
        "",
        {"name": "bad", "data": "%%%"},
        {"name": "empty", "data": ""},
        {"name": "bad", "data": "YQ==", "url": "https://example.com"},
        {"name": "big", "data": base64.b64encode(b"x" * (1024 * 1024 + 1)).decode()},
    ],
)
def test_invalid_files_do_not_create_contacts_or_submissions(client, workspace, value):
    create_form(
        client,
        workspace,
        fields=[
            *FIELDS,
            {"id": "attachment", "label": "File", "type": "file_upload", "required": True},
        ],
    )
    assert (
        APIClient().post("/api/public/forms/enquiry/", body(value), format="json").status_code
        == 400
    )
    assert not FormSubmission.objects.for_workspace(workspace).exists()


def test_signature_requires_png_and_retention_removes_download_bytes(client, workspace):
    form = create_form(
        client,
        workspace,
        fields=[
            *FIELDS,
            {"id": "attachment", "label": "Signature", "type": "signature", "required": True},
        ],
    )
    assert (
        APIClient()
        .post(
            "/api/public/forms/enquiry/", body({"name": "fake.png", "data": "YQ=="}), format="json"
        )
        .status_code
        == 400
    )
    value = {
        "name": "signature.png",
        "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=",
    }
    assert (
        APIClient().post("/api/public/forms/enquiry/", body(value), format="json").status_code
        == 201
    )
    row = FormSubmission.objects.for_workspace(workspace).get()
    url = f"/api/workspaces/{workspace.pk}/forms/{form['id']}/submissions/{row.pk}/attachment/file/"
    assert client.get(url).status_code == 200
    row.answers = "{}"
    row.save(update_fields=["answers"])
    assert client.get(url).status_code == 404
