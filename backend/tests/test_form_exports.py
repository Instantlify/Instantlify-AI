import csv
import io
import json
import uuid

import pytest
from rest_framework.test import APIClient

from apps.tools.models import FormSubmission
from tests.test_portal_tools import create_form

pytestmark = pytest.mark.django_db


def test_export_includes_all_rows_not_only_response_preview_and_preserves_history(
    client, workspace
):
    form = create_form(client, workspace)
    FormSubmission.all_objects.bulk_create(
        [
            FormSubmission(
                workspace=workspace,
                form_id=uuid.UUID(form["id"]),
                request_id=uuid.uuid4(),
                answers=json.dumps(
                    {
                        "name": f"Person {i}",
                        "email": f"p{i}@example.com",
                        "old_removed_answer": "Still present",
                    }
                ),
                consent_text="Contact me",
            )
            for i in range(501)
        ]
    )
    url = f"/api/workspaces/{workspace.pk}/forms/{form['id']}/submissions/export/"
    response = client.get(url)
    rows = json.loads(b"".join(response.streaming_content))
    assert len(rows) == 501 and rows[-1]["answers"]["old_removed_answer"] == "Still present"
    assert APIClient().get(url).status_code == 403


def test_csv_escapes_spreadsheet_formulas_and_joins_multi_answers(client, workspace):
    form = create_form(client, workspace)
    FormSubmission.objects.for_workspace(workspace).create(
        workspace=workspace,
        form_id=form["id"],
        request_id=uuid.uuid4(),
        answers=json.dumps(
            {
                "name": ' =HYPERLINK("https://example.com")',
                "email": "p@example.com",
                "choices": ["A", "B"],
            }
        ),
        consent_text="Contact me",
    )
    response = client.get(
        f"/api/workspaces/{workspace.pk}/forms/{form['id']}/submissions/export/?file_type=csv"
    )
    rows = list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode("utf-8-sig"))))
    assert len(rows) == 2 and rows[1][3].startswith("' =HYPERLINK")
    assert json.loads(rows[1][-1])["choices"] == ["A", "B"]
