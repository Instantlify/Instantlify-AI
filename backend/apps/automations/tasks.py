from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.crm.services import queue_reply
from apps.platform_ops.security import blocked, pause_guard
from apps.tenants.dispatch import enqueue_once, release

from .models import ConversationState


@shared_task(ignore_result=True)
def dispatch_runs():
    for workspace_id, pk in ConversationState.all_objects.filter(
        status="running", available_at__lte=timezone.now()
    ).values_list("workspace_id", "pk")[:100]:
        enqueue_once(step, workspace_id, pk)


@shared_task(ignore_result=True)
@pause_guard("automations")
def step(workspace_id, state_id):
    with transaction.atomic():
        state = (
            ConversationState.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=state_id, status="running", available_at__lte=timezone.now())
            .first()
        )
        if not state:
            return
        if blocked(workspace_id, "automations", f"automation:{state.automation_id}"):
            return
        if state.steps >= 100 or state.conversation.identity.lead.opted_out:
            state.status = "stopped"
            state.error_code = "execution_guard"
            state.save()
            return
        try:
            node = next(n for n in state.graph["nodes"] if n["id"] == state.node_id)
            data = node["data"]
            kind = data["kind"]
            if kind == "end":
                state.status = "completed"
                state.save()
                return
            if kind == "wait":
                state.status = "waiting"
                state.save()
                return
            branch = ""
            if kind in {"send_message", "send_buttons"}:
                text = data["text"]
                for key, value in state.variables.items():
                    text = text.replace("{{" + key + "}}", str(value)[:500])
                queue_reply(
                    state.conversation,
                    text,
                    f"flow:{state.id}:{state.last_message_id}:{state.steps}",
                    buttons=data.get("buttons"),
                    private_reply_id=state.variables.get("comment_id"),
                    automation_id=state.automation_id,
                )
                state.variables.pop("comment_id", None)
            elif kind == "delay":
                state.available_at = timezone.now() + timedelta(seconds=int(data["seconds"]))
            elif kind in {"condition", "branch"}:
                branch = (
                    "true"
                    if str(state.variables.get(data.get("variable", "last_text"), "")).casefold()
                    == str(data.get("equals", "")).casefold()
                    else "false"
                )
            state.node_id = next(
                e["target"]
                for e in state.graph["edges"]
                if e["source"] == state.node_id and e.get("sourceHandle", "") == branch
            )
            state.steps += 1
        except (KeyError, StopIteration, ValueError, ValidationError):
            state.status = "failed"
            state.error_code = "invalid_transition_or_delivery_guard"
        state.save()
        if state.status == "running":
            # The next node is due now; do not make it wait out the dispatch marker.
            transaction.on_commit(lambda: release(step, state_id))
