import json
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import WorkflowActionJob


def validate_followers(graph):
    for node in graph["nodes"]:
        data = node["data"]
        if data["kind"] != "follow_gate":
            continue
        if any(trigger.get("channel") != "instagram" for trigger in graph["triggers"]):
            raise ValidationError("Follower verification requires Instagram triggers.")
        for name, limit in [("text", 2000), ("button_title", 20), ("expected_reply", 64)]:
            value = data.get(name)
            if (
                not isinstance(value, str)
                or not value.strip()
                or (len(value.encode()) if name == "expected_reply" else len(value)) > limit
            ):
                raise ValidationError(
                    "Add a follow request, a short button label and a reply payload."
                )


def request_follow(state, data):
    from apps.crm.services import queue_reply

    text = data["text"]
    for name, value in state.variables.items():
        text = text.replace("{{" + name + "}}", str(value)[:500])
    queue_reply(
        state.conversation,
        text,
        f"follow:{state.run_token}:{state.node_id}:{state.last_message_id}",
        buttons=[
            {"type": "postback", "title": data["button_title"], "payload": data["expected_reply"]}
        ],
        private_reply_id=state.variables.get("comment_id"),
        automation_id=state.automation_id,
    )
    state.variables.pop("comment_id", None)
    state.status = "waiting"
    state.save()


def follow_step(state, data):
    from apps.crm.models import Message

    if (
        Message.objects.for_workspace(state.workspace_id)
        .filter(pk=state.last_message_id, kind__in=["comment", "live_comment"])
        .exists()
    ):
        request_follow(state, data)
        return False
    job, _ = WorkflowActionJob.objects.for_workspace(state.workspace_id).get_or_create(
        key=f"follow:{state.run_token}:{state.node_id}:{state.last_message_id}",
        defaults={
            "workspace_id": state.workspace_id,
            "state": state,
            "kind": "follow_gate",
            "payload": json.dumps(
                {"message_id": str(state.last_message_id), "run_token": str(state.run_token)}
            ),
            "available_at": timezone.now(),
        },
    )
    if job.status in {"pending", "executing"}:
        state.available_at = timezone.now() + timedelta(seconds=5)
        state.save()
        return False
    if job.status != "complete":
        raise ValidationError(
            "The provider could not verify follow status. Reconnect the account and review this run."
        )
    if json.loads(job.result).get("following") is True:
        state.variables["following"] = True
        return True
    request_follow(state, data)
    return False


def execute_follow_check(workspace_id, job_id):
    from apps.billing.gating import check_connection_unlocked
    from apps.channels.adapters import adapter_for
    from apps.crm.models import Message
    from apps.platform_ops.security import blocked
    from apps.tenants.services import audit

    with transaction.atomic():
        job = (
            WorkflowActionJob.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=job_id, status="pending")
            .select_related(
                "state__conversation__identity__lead", "state__conversation__identity__connection"
            )
            .first()
        )
        if not job:
            return
        state = job.state
        if blocked(workspace_id, "automations", f"automation:{state.automation_id}"):
            return
        connection = state.conversation.identity.connection
        message = (
            Message.objects.for_workspace(workspace_id)
            .filter(pk=json.loads(job.payload)["message_id"], conversation=state.conversation)
            .first()
        )
        if (
            state.status != "running"
            or json.loads(job.payload).get("run_token") != str(state.run_token)
            or state.conversation.identity.lead.opted_out
            or not message
            or message.kind in {"comment", "live_comment"}
            or connection.provider != "instagram"
            or connection.status != "active"
            or connection.expires_at <= timezone.now()
        ):
            job.status, job.error_code = "needs_review", "follow_context_unavailable"
            job.save()
            return
        job.status, job.available_at = "executing", timezone.now()
        job.save()
    try:
        check_connection_unlocked(connection)
        following = adapter_for(connection).following_status(
            state.conversation.identity.external_id
        )
        if not isinstance(following, bool):
            raise ValidationError("unknown_follow_status")
        job.status, job.result = "complete", json.dumps({"following": following})
    except Exception:
        job.status, job.error_code = "needs_review", "follow_status_unavailable"
    job.save()
    audit(job.workspace, None, "workflow_follow." + job.status, job.pk)
