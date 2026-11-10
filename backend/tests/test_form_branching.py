import json
import uuid

import pytest
from rest_framework.test import APIClient

from apps.tools.models import FormSubmission
from tests.test_portal_tools import FIELDS, create_form

pytestmark = pytest.mark.django_db


def submit(answers):
    return APIClient().post(
        "/api/public/forms/enquiry/",
        {
            "answers": answers,
            "request_id": str(uuid.uuid4()),
            "consent": True,
        },
        format="json",
    )


def test_branch_path_discards_hidden_answers_and_requires_only_visible_questions(client, workspace):
    fields = [
        *FIELDS,
        {"id": "choice", "label": "Choose", "type": "yes_no", "required": True},
        {"id": "details", "label": "Details", "type": "text", "required": True},
        {"id": "finish", "label": "Finish", "type": "text", "required": True},
    ]
    form = create_form(
        client,
        workspace,
        fields=fields,
        branching=[{"field_id": "choice", "answer": "no", "next_id": "finish"}],
    )
    answers = {
        "name": "P",
        "email": "p@example.com",
        "choice": "no",
        "details": "forged hidden answer",
        "finish": "Done",
    }
    assert submit(answers).status_code == 201
    saved = json.loads(FormSubmission.objects.for_workspace(workspace).get().answers)
    assert "details" not in saved
    assert submit({**answers, "choice": "yes", "details": ""}).status_code == 400
    public = APIClient().get("/api/public/forms/enquiry/").json()
    assert public["branching"] == form["branching"]
    assert "submission_actions" not in public


@pytest.mark.parametrize(
    "rule",
    [
        {"field_id": "name", "answer": "P", "next_id": None},
        {"field_id": "email", "answer": "P", "next_id": "name"},
        {"field_id": "email", "answer": "P", "next_id": "missing"},
        {"field_id": "email", "answer": [], "next_id": None},
    ],
)
def test_invalid_branches_cannot_skip_email_or_loop(client, workspace, rule):
    response = client.post(
        f"/api/workspaces/{workspace.pk}/forms/",
        {
            "title": "Bad",
            "slug": "bad",
            "fields": FIELDS,
            "branching": [rule],
        },
        format="json",
    )
    assert response.status_code == 400


def test_patch_cannot_leave_dangling_branch(client, workspace):
    form = create_form(
        client,
        workspace,
        branching=[{"field_id": "email", "answer": "p@example.com", "next_id": None}],
    )
    response = client.patch(
        f"/api/workspaces/{workspace.pk}/forms/{form['id']}/",
        {"fields": [FIELDS[1]]},
        format="json",
    )
    assert response.status_code == 200
    response = client.patch(
        f"/api/workspaces/{workspace.pk}/forms/{form['id']}/",
        {"branching": [{"field_id": "name", "answer": "P", "next_id": None}]},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "kind,config,valid,invalid",
    [
        ("number", {"min": 1, "max": 10}, "2.5", "NaN"),
        ("number", {"min": 1, "max": 10}, "2", "11"),
        ("date", {}, "2028-02-29", "2027-02-29"),
        ("url", {}, "https://example.com", "javascript:alert(1)"),
        ("checkboxes", {"options": ["A", "B"]}, ["A", "B"], ["A", "C"]),
        ("yes_no", {}, "no", "maybe"),
        ("rating", {}, "5", "5.5"),
        ("opinion_scale", {}, "0", "11"),
    ],
)
def test_rich_answers_are_validated_and_saved_encrypted(
    client, workspace, kind, config, valid, invalid
):
    create_form(
        client,
        workspace,
        fields=[
            *FIELDS,
            {"id": "answer", "label": "Answer", "type": kind, "required": True, **config},
        ],
    )
    base = {"name": "P", "email": "p@example.com"}
    assert submit({**base, "answer": invalid}).status_code == 400
    assert submit({**base, "answer": valid}).status_code == 201
    assert (
        json.loads(FormSubmission.objects.for_workspace(workspace).get().answers)["answer"] == valid
    )


def test_required_multi_choice_cannot_be_empty_or_duplicated(client, workspace):
    create_form(
        client,
        workspace,
        fields=[
            *FIELDS,
            {
                "id": "choices",
                "label": "Choices",
                "type": "checkboxes",
                "required": True,
                "options": ["A", "B"],
            },
        ],
    )
    for value in ([], ["A", "A"], "A"):
        assert submit({"name": "P", "email": "p@example.com", "choices": value}).status_code == 400


def test_completion_settings_tags_and_closed_form(client, workspace):
    from apps.crm.models import Lead

    lead = Lead.objects.for_workspace(workspace).create(
        workspace=workspace, email="p@example.com", tags=["existing"], opted_out=True
    )
    form = create_form(
        client,
        workspace,
        theme={"primary": "#10244a"},
        button_align="center",
        redirect_url="https://example.com/thanks",
        submission_tags=["new", "new"],
    )
    response = submit({"name": "P", "email": "p@example.com"})
    assert response.status_code == 201
    assert response.json()["redirect_url"] == "https://example.com/thanks"
    lead.refresh_from_db()
    assert lead.tags == ["existing", "new"] and lead.opted_out
    public = APIClient().get("/api/public/forms/enquiry/").json()
    assert public["theme"] == {"primary": "#10244a"} and public["button_align"] == "center"
    assert "submission_tags" not in public
    url = f"/api/workspaces/{workspace.pk}/forms/{form['id']}/"
    assert client.patch(url, {"closed": True}, format="json").status_code == 200
    assert submit({"name": "P", "email": "p@example.com"}).status_code == 404
    assert APIClient().get("/api/public/forms/enquiry/").status_code == 404
    assert client.get(url).json()["submissions"] == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"theme": {"background": "url(https://example.com)"}},
        {"theme": {"unknown": "#ffffff"}},
        {"theme": {"text": "#ffffff", "background": "#ffffff"}},
        {"redirect_url": "javascript:alert(1)"},
        {"button_align": "absolute"},
        {"submission_tags": [""]},
        {"fields": [*FIELDS, {"id": "bad", "label": "Bad", "type": []}]},
    ],
)
def test_invalid_presentation_and_question_types_rejected(client, workspace, patch):
    response = client.post(
        f"/api/workspaces/{workspace.pk}/forms/",
        {"title": "Bad", "slug": "bad", "fields": FIELDS, **patch},
        format="json",
    )
    assert response.status_code == 400
