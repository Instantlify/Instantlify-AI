"""Durable canvas execution for consented form contacts without inventing a channel."""

import hashlib
import json
from datetime import timedelta
from types import SimpleNamespace

from celery import shared_task
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.automations.conditions import evaluate
from apps.automations.models import Automation
from apps.automations.services import delay_seconds, validate_graph
from apps.billing.gating import PlanLimitExceeded, check_feature
from apps.crm.models import IntegrationConfig, IntegrationJob, Lead
from apps.platform_ops.security import blocked, pause_guard
from apps.public_api.services import lead_payload
from apps.tenants.dispatch import enqueue_once, release
from apps.tenants.models import Membership

from .models import FormSubmission

CONTACT_NODES = {
    "end",
    "condition",
    "branch",
    "randomizer",
    "delay",
    "add_tag",
    "set_field",
    "set_stage",
    "assign_member",
    "integration_action",
    "transfer",
}


def compatible_graph(graph):
    validate_graph(graph)
    if any(node["data"]["kind"] not in CONTACT_NODES for node in graph["nodes"]):
        raise ValidationError(
            "Form-only contacts support conditions, random paths, delays, tags, fields, stages, assignments, integrations and transfers. Messaging, calls and reply waits need a verified channel conversation."
        )


def queue_workflow(submission, form, lead, answers):
    if not form.automation_id:
        return
    automation = (
        Automation.objects.for_workspace(form.workspace_id)
        .filter(pk=form.automation_id, enabled=True)
        .first()
    )
    if not lead or lead.opted_out or not automation:
        submission.workflow_status = "stopped"
        submission.workflow_state = json.dumps({"error": "contact_or_automation_unavailable"})
    else:
        try:
            compatible_graph(automation.published)
        except ValidationError:
            submission.workflow_status = "needs_review"
            submission.workflow_state = json.dumps({"error": "channel_required_or_invalid_graph"})
        else:
            submission.workflow_status = "running"
            submission.workflow_due_at = timezone.now()
            submission.workflow_state = json.dumps(
                {
                    "automation_id": str(automation.pk),
                    "graph": automation.published,
                    "node_id": automation.published["start"],
                    "variables": {
                        "form": answers,
                        **{
                            key: value
                            for key, value in answers.items()
                            if key not in {"last_text", "comment_id"}
                        },
                        "email": lead.email,
                        "name": lead.name,
                    },
                    "steps": 0,
                }
            )
    submission.save(update_fields=["workflow_state", "workflow_status", "workflow_due_at"])


@shared_task(ignore_result=True)
def dispatch_form_workflows():
    for wid, pk in FormSubmission.all_objects.filter(
        workflow_status="running", workflow_due_at__lte=timezone.now()
    ).values_list("workspace_id", "pk")[:100]:
        enqueue_once(step_form_workflow, wid, pk)


def render(value, variables):
    if isinstance(value, str):
        for key, replacement in variables.items():
            value = value.replace("{{" + key + "}}", str(replacement)[:500])
        return value
    if isinstance(value, list):
        return [render(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: render(item, variables) for key, item in value.items()}
    return value


def integration_node(submission, state, data, lead):
    check_feature(submission.workspace_id, "integrations_unlocked")
    config = (
        IntegrationConfig.objects.for_workspace(submission.workspace_id)
        .filter(pk=data["integration_id"], enabled=True, status="active")
        .first()
    )
    if not config:
        raise ValidationError("Integration unavailable")
    variables = state["variables"]
    payload = lead_payload(lead)
    payload.update(
        text=render(data.get("text", ""), variables)[:2000],
        _form_flow={"automation_id": state["automation_id"]},
    )
    if data["operation"] == "send_email":
        from django.core.validators import validate_email

        payload.update(
            to=render(data.get("to") or lead.email, variables),
            subject=render(data["subject"], variables)[:200],
        )
        validate_email(payload["to"])
    if data["operation"] == "webhook":
        payload["request"] = render(json.loads(data.get("request_body", "{}")), variables)
    job, _ = IntegrationJob.objects.for_workspace(submission.workspace_id).get_or_create(
        idempotency_key=f"form-flow:{submission.pk}:{state['steps']}",
        defaults={
            "workspace_id": submission.workspace_id,
            "integration": config,
            "form_submission": submission,
            "operation": data["operation"],
            "payload": json.dumps(payload, default=str),
            "available_at": timezone.now(),
        },
    )
    if job.status in {"pending", "executing"}:
        submission.workflow_due_at = timezone.now() + timedelta(seconds=5)
        return False
    if job.status != "complete" or len(job.result) > 20000:
        raise ValidationError("Integration needs review")
    result = json.loads(job.result)
    variables[data.get("variable", "integration_result")] = result
    mapping = data.get("response_map", {})
    if isinstance(mapping, str):
        mapping = json.loads(mapping)
    for name, path in mapping.items():
        value = result
        for part in path.split("."):
            value = value[int(part)] if isinstance(value, list) else value[part]
        variables[name] = value
    if len(json.dumps(variables)) > 50000:
        raise ValidationError("Variables too large")
    return True


@shared_task(ignore_result=True)
@pause_guard("automations")
def step_form_workflow(workspace_id, submission_id):
    with transaction.atomic():
        submission = (
            FormSubmission.objects.for_workspace(workspace_id)
            .select_for_update()
            .select_related("form")
            .filter(
                pk=submission_id, workflow_status="running", workflow_due_at__lte=timezone.now()
            )
            .first()
        )
        if not submission:
            return
        state = json.loads(submission.workflow_state)
        trace = state.setdefault("trace", [])
        if blocked(workspace_id, "automations", f"automation:{state.get('automation_id', '')}"):
            return
        try:
            lead = (
                Lead.objects.for_workspace(workspace_id)
                .select_for_update()
                .get(pk=submission.lead_id, opted_out=False)
            )
            automation = Automation.objects.for_workspace(workspace_id).get(
                pk=state["automation_id"], enabled=True
            )
            if not submission.form.published or state["steps"] >= 100:
                raise ValidationError("Execution stopped")
            compatible_graph(state["graph"])
            data = next(
                node["data"] for node in state["graph"]["nodes"] if node["id"] == state["node_id"]
            )
            kind, branch = data["kind"], ""
            trace.append(
                {
                    "node_id": state["node_id"],
                    "kind": kind,
                    "step": state["steps"],
                    "at": timezone.now().isoformat(),
                }
            )
            state["trace"] = trace[-100:]
            variables = state["variables"]
            submission.workflow_due_at = timezone.now()
            if kind == "end":
                submission.workflow_status = "completed"
            elif kind == "transfer":
                target = Automation.objects.for_workspace(workspace_id).get(
                    pk=data["automation_id"], enabled=True
                )
                compatible_graph(target.published)
                state.update(
                    automation_id=str(target.pk),
                    graph=target.published,
                    node_id=target.published["start"],
                    steps=state["steps"] + 1,
                )
            else:
                waiting = False
                if kind == "integration_action":
                    waiting = not integration_node(submission, state, data, lead)
                elif kind == "delay":
                    proxy = SimpleNamespace(
                        id=submission.pk,
                        run_token=submission.pk,
                        node_id=state["node_id"],
                        steps=state["steps"],
                    )
                    submission.workflow_due_at = timezone.now() + timedelta(
                        seconds=delay_seconds(proxy, data)
                    )
                elif kind == "randomizer":
                    seed = f"{submission.pk}:{state['steps']}:{state['node_id']}"
                    branch = (
                        "true"
                        if int(hashlib.sha256(seed.encode()).hexdigest(), 16) % 100
                        < data.get("percentage", 50)
                        else "false"
                    )
                elif kind in {"condition", "branch"}:
                    branch = (
                        "true"
                        if evaluate(
                            data,
                            {
                                "variables": variables,
                                "fields": lead.fields,
                                "tags": lead.tags,
                                "stage": lead.stage,
                                "email": lead.email,
                                "channel": "form",
                            },
                        )
                        else "false"
                    )
                elif kind == "assign_member":
                    member = Membership.objects.for_workspace(workspace_id).get(
                        user_id=data["user_id"], user__is_active=True
                    )
                    lead.assigned_to_id = member.user_id
                    lead.save(update_fields=["assigned_to"])
                else:
                    from apps.automations.guided import apply_action

                    proxy = SimpleNamespace(
                        workspace_id=workspace_id,
                        automation_id=automation.pk,
                        variables=variables,
                        conversation=SimpleNamespace(
                            identity=SimpleNamespace(lead_id=lead.pk),
                            workspace=submission.workspace,
                        ),
                    )
                    apply_action(proxy, data)
                if not waiting:
                    state["node_id"] = next(
                        edge["target"]
                        for edge in state["graph"]["edges"]
                        if edge["source"] == state["node_id"]
                        and edge.get("sourceHandle", "") == branch
                    )
                    state["steps"] += 1
        except (
            PlanLimitExceeded,
            DjangoValidationError,
            ValidationError,
            KeyError,
            ValueError,
            StopIteration,
            Lead.DoesNotExist,
            Automation.DoesNotExist,
            Membership.DoesNotExist,
            IndexError,
            TypeError,
        ):
            state["error"] = "invalid_transition_or_contact_guard"
            submission.workflow_status = "needs_review"
        submission.workflow_state = json.dumps(state)
        if submission.workflow_status != "running":
            submission.workflow_due_at = None
        submission.save(update_fields=["workflow_state", "workflow_status", "workflow_due_at"])

        if submission.workflow_status == "running":
            transaction.on_commit(lambda: release(step_form_workflow, submission.pk))
