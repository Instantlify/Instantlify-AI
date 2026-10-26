import json
import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.crm.models import IntegrationJob, Lead
from apps.crm.tasks import process_integration
from apps.public_api.models import OutboundWebhook, WebhookSubscription
from apps.tools.models import FormSubmission
from tests.conftest import set_limits
from tests.test_marketing_integrations import integration
from tests.test_portal_tools import create_form

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def quiet_realtime_notifications():
    with patch("apps.crm.services.notify"):
        yield


def action(config):
    return {
        "integration_id": str(config.pk),
        "operation": "send_email",
        "subject": "Thanks {{name}}",
        "text": "Hello {{name}}, we received your enquiry.",
    }


def submit():
    return {
        "request_id": str(uuid.uuid4()),
        "consent": True,
        "answers": {"name": "A Person", "email": "person@example.com"},
    }


def test_form_actions_are_durable_and_replayed_submissions_do_not_duplicate_them(client, workspace):
    config = integration(workspace, "zorromail", sender_email="sender@example.com")
    form = create_form(client, workspace, submission_actions=[action(config)])
    WebhookSubscription.objects.for_workspace(workspace).create(
        workspace=workspace,
        url="https://example.com/form-hook",
        secret="private",
        events=["form.submitted"],
    )
    anonymous, body = APIClient(), submit()
    for _ in range(2):
        assert anonymous.post("/api/public/forms/enquiry/", body, format="json").status_code in {
            200,
            201,
        }
    assert IntegrationJob.objects.for_workspace(workspace).count() == 1
    assert (
        OutboundWebhook.objects.for_workspace(workspace).filter(event="form.submitted").count() == 1
    )
    job = IntegrationJob.objects.for_workspace(workspace).get()
    assert job.form_submission_id == FormSubmission.objects.for_workspace(workspace).get().pk
    assert json.loads(job.payload)["to"] == "person@example.com"
    assert json.loads(job.payload)["subject"] == "Thanks A Person"
    with patch("apps.crm.tasks.integration_for") as provider:
        provider.return_value.execute.return_value = {"id": "mail-one", "accepted": True}
        process_integration(str(workspace.pk), str(job.pk))
        process_integration(str(workspace.pk), str(job.pk))
    provider.return_value.execute.assert_called_once()
    response = client.get(f"/api/workspaces/{workspace.pk}/forms/{form['id']}/submissions/")
    assert response.json()[0]["actions"][0]["status"] == "complete"
    assert response.json()[0]["actions"][0]["accepted"] is True


@pytest.mark.parametrize("initial_opt_out", [False, True])
def test_existing_and_late_opt_outs_prevent_form_followups(client, workspace, initial_opt_out):
    config = integration(workspace, "zorromail", sender_email="sender@example.com")
    create_form(client, workspace, submission_actions=[action(config)])
    lead = Lead.objects.for_workspace(workspace).create(
        workspace=workspace, email="person@example.com", opted_out=initial_opt_out
    )
    assert (
        APIClient().post("/api/public/forms/enquiry/", submit(), format="json").status_code == 201
    )
    lead.opted_out = True
    lead.save()
    job = IntegrationJob.objects.for_workspace(workspace).get()
    with patch("apps.crm.tasks.integration_for") as provider:
        process_integration(str(workspace.pk), str(job.pk))
    provider.assert_not_called()
    job.refresh_from_db()
    assert (
        job.status == "needs_review"
        and json.loads(job.result)["error"] == "form_or_contact_unavailable"
    )


def test_deleted_integration_does_not_lose_the_form_response(client, workspace):
    config = integration(workspace, "zorromail", sender_email="sender@example.com")
    form = create_form(client, workspace, submission_actions=[action(config)])
    config.delete()
    assert (
        APIClient().post("/api/public/forms/enquiry/", submit(), format="json").status_code == 201
    )
    response = client.get(f"/api/workspaces/{workspace.pk}/forms/{form['id']}/submissions/").json()[
        0
    ]
    assert response["action_errors"] == [{"action": 1, "error": "integration_unavailable"}]
    assert response["answers"]["email"] == "person@example.com"


def test_incompatible_or_foreign_form_integrations_are_rejected(client, workspace, user):
    from apps.tenants.services import create_workspace

    config = integration(workspace, "slack")
    other = create_workspace(user, "Other form tenant")
    foreign = integration(other, "zorromail")
    for candidate in [config, foreign]:
        response = client.post(
            f"/api/workspaces/{workspace.pk}/forms/",
            {
                "title": "Form",
                "slug": "test-form",
                "fields": [{"id": "email", "label": "Email", "type": "email", "required": True}],
                "submission_actions": [action(candidate)],
            },
            format="json",
        )
        assert response.status_code == 400


def test_plan_gate_is_rechecked_after_form_submission(client, workspace):
    config = integration(workspace, "zorromail", sender_email="sender@example.com")
    create_form(client, workspace, submission_actions=[action(config)])
    assert (
        APIClient().post("/api/public/forms/enquiry/", submit(), format="json").status_code == 201
    )
    set_limits(workspace, integrations_unlocked=False)
    job = IntegrationJob.objects.for_workspace(workspace).get()
    with patch("apps.crm.tasks.integration_for") as provider:
        process_integration(str(workspace.pk), str(job.pk))
    provider.assert_not_called()
    job.refresh_from_db()
    assert json.loads(job.result)["error"] == "plan_limit"


def test_form_webhook_action_contains_structured_answers(client, workspace):
    config = integration(workspace, "webhook")
    create_form(
        client,
        workspace,
        submission_actions=[{"integration_id": str(config.pk), "operation": "webhook"}],
    )
    assert (
        APIClient().post("/api/public/forms/enquiry/", submit(), format="json").status_code == 201
    )
    job = IntegrationJob.objects.for_workspace(workspace).get()
    assert json.loads(job.payload)["request"]["answers"]["email"] == "person@example.com"
    assert json.loads(job.payload)["request"]["event"] == "form.submitted"
