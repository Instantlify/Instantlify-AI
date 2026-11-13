import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.automations.models import Automation
from apps.crm.models import Conversation, IntegrationJob, Lead
from apps.tools.form_workflows import step_form_workflow
from apps.tools.models import FormSubmission
from tests.test_marketing_integrations import integration
from tests.test_portal_tools import create_form

pytestmark = pytest.mark.django_db


def graph(*actions):
    actions = [*actions, {"kind": "end"}]
    return {
        "start": "n0",
        "triggers": [{"kind": "dm", "keyword": "form"}],
        "nodes": [{"id": f"n{i}", "data": data} for i, data in enumerate(actions)],
        "edges": [{"source": f"n{i}", "target": f"n{i + 1}"} for i in range(len(actions) - 1)],
    }


def prepare(client, workspace, *actions):
    flow = Automation.objects.for_workspace(workspace).create(
        workspace=workspace, name="Enquiries", enabled=True, published=graph(*actions)
    )
    form = create_form(client, workspace, automation_id=str(flow.pk))
    payload = {
        "request_id": str(uuid.uuid4()),
        "consent": True,
        "answers": {"name": "Alex", "email": "person@example.com"},
    }
    anonymous = APIClient()
    assert anonymous.post("/api/public/forms/enquiry/", payload, format="json").status_code == 201
    assert anonymous.post("/api/public/forms/enquiry/", payload, format="json").status_code == 200
    return flow, form, FormSubmission.objects.for_workspace(workspace).get()


def step(row):
    with patch("apps.crm.services.notify"):
        step_form_workflow(str(row.workspace_id), str(row.pk))
    row.refresh_from_db()


def test_form_only_contact_runs_canvas_without_fabricating_a_conversation(client, workspace):
    _, form, row = prepare(
        client,
        workspace,
        {"kind": "add_tag", "tag": "enquiry"},
        {"kind": "set_field", "field": "greeting", "value": "Hello {{name}}"},
        {"kind": "set_stage", "stage": "qualified"},
    )
    for _ in range(5):
        step(row)
    assert row.workflow_status == "completed"
    lead = Lead.objects.for_workspace(workspace).get()
    assert lead.tags == ["enquiry"] and lead.fields["greeting"] == "Hello Alex"
    assert lead.stage == "qualified"
    assert not Conversation.objects.for_workspace(workspace).exists()
    assert FormSubmission.objects.for_workspace(workspace).count() == 1
    result = client.get(f"/api/workspaces/{workspace.pk}/forms/{form['id']}/submissions/").json()[0]
    assert result["workflow_status"] == "completed"
    assert "workflow_state" not in result


def test_form_workflow_delay_persists_and_honours_due_time(client, workspace):
    _, _, row = prepare(
        client, workspace, {"kind": "delay", "seconds": 60}, {"kind": "add_tag", "tag": "later"}
    )
    step(row)
    assert row.workflow_due_at > timezone.now() + timedelta(seconds=50)
    step(row)
    row.lead.refresh_from_db()
    assert not row.lead.tags
    row.workflow_due_at = timezone.now()
    row.save()
    step(row)
    row.lead.refresh_from_db()
    assert row.lead.tags == ["later"]


def test_opt_out_or_disabled_automation_stops_execution(client, workspace):
    flow, _, row = prepare(client, workspace, {"kind": "add_tag", "tag": "never"})
    flow.enabled = False
    flow.save()
    step(row)
    assert row.workflow_status == "needs_review"
    row.lead.refresh_from_db()
    assert not row.lead.tags


def test_messaging_graph_cannot_be_attached_to_unverified_form_identity(client, workspace):
    flow = Automation.objects.for_workspace(workspace).create(
        workspace=workspace,
        name="DM",
        enabled=True,
        published=graph({"kind": "send_message", "text": "Hello"}),
    )
    response = client.post(
        f"/api/workspaces/{workspace.pk}/forms/",
        {"title": "Bad", "slug": "bad", "fields": [], "automation_id": str(flow.pk)},
        format="json",
    )
    assert response.status_code == 400
    assert "verified channel" in str(response.json())


def test_form_flow_integration_is_durable_and_does_not_requeue(client, workspace):
    config = integration(workspace, "zorromail", sender_email="sender@example.com")
    _, _, row = prepare(
        client,
        workspace,
        {
            "kind": "integration_action",
            "integration_id": str(config.pk),
            "operation": "send_email",
            "text": "Hello {{name}}",
            "subject": "Enquiry",
            "variable": "mail",
        },
    )
    step(row)
    row.workflow_due_at = timezone.now()
    row.save()
    step(row)
    jobs = IntegrationJob.objects.for_workspace(workspace)
    assert jobs.count() == 1
    job = jobs.get()
    assert job.form_submission == row
    assert json.loads(job.payload)["to"] == "person@example.com"
    job.status, job.result = "complete", json.dumps({"accepted": True})
    job.save()
    row.workflow_due_at = timezone.now()
    row.save()
    step(row)
    step(row)
    assert row.workflow_status == "completed"
    assert json.loads(row.workflow_state)["variables"]["mail"]["accepted"]


def test_workflow_snapshot_is_retained_and_opt_out_is_rechecked(client, workspace):
    flow, _, row = prepare(client, workspace, {"kind": "add_tag", "tag": "original"})
    flow.published = graph({"kind": "add_tag", "tag": "changed"})
    flow.save()
    step(row)
    row.lead.refresh_from_db()
    assert row.lead.tags == ["original"]
    row.lead.opted_out = True
    row.lead.save()
    step(row)
    assert row.workflow_status == "needs_review"


def test_form_cannot_select_another_workspaces_workflow(client, workspace, user):
    from apps.tenants.services import create_workspace

    other = create_workspace(user, "Other")
    flow = Automation.objects.for_workspace(other).create(
        workspace=other, name="Private", enabled=True, published=graph()
    )
    response = client.post(
        f"/api/workspaces/{workspace.pk}/forms/",
        {"title": "No", "slug": "no", "fields": [], "automation_id": str(flow.pk)},
        format="json",
    )
    assert response.status_code == 400
    assert "this workspace" in str(response.json())


def test_disabled_flow_does_not_send_a_queued_integration_action(client, workspace):
    from apps.crm.tasks import process_integration

    config = integration(workspace, "zorromail", sender_email="sender@example.com")
    flow, _, row = prepare(
        client,
        workspace,
        {
            "kind": "integration_action",
            "integration_id": str(config.pk),
            "operation": "send_email",
            "text": "Thanks",
            "subject": "Enquiry",
        },
    )
    step(row)
    job = IntegrationJob.objects.for_workspace(workspace).get()
    flow.enabled = False
    flow.save()
    with patch("apps.crm.tasks.integration_for") as provider:
        process_integration(str(workspace.pk), str(job.pk))
    provider.assert_not_called()
    job.refresh_from_db()
    assert job.status == "needs_review"
