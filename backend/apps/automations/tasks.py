import hashlib
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.crm.services import queue_reply
from apps.platform_ops.security import blocked, pause_guard
from apps.tenants.dispatch import enqueue_once, release

from .models import ConversationState, WorkflowActionJob


@shared_task(ignore_result=True)
def dispatch_runs():
    WorkflowActionJob.all_objects.filter(
        kind="avatar_video",
        status="polling",
        available_at__lt=timezone.now() - timedelta(minutes=5),
    ).update(status="rendering")
    WorkflowActionJob.all_objects.filter(
        kind="avatar_video",
        status="rendering",
        created_at__lt=timezone.now() - timedelta(minutes=30),
    ).update(status="needs_review", error_code="avatar_render_timeout")
    WorkflowActionJob.all_objects.filter(
        status="executing", available_at__lt=timezone.now() - timedelta(minutes=5)
    ).update(status="needs_review", error_code="worker_interrupted")
    WorkflowActionJob.all_objects.filter(
        kind="ai_call",
        status="call_polling",
        available_at__lt=timezone.now() - timedelta(minutes=5),
    ).update(status="calling")
    for wid, pk, kind in WorkflowActionJob.all_objects.filter(
        status__in=["pending", "rendering", "calling"], available_at__lte=timezone.now()
    ).values_list("workspace_id", "pk", "kind")[:100]:
        task = (
            process_follow_job
            if kind == "follow_gate"
            else process_voice_job
            if kind == "generate_voice"
            else process_ai_job
        )
        enqueue_once(
            process_avatar_job
            if kind == "avatar_video"
            else process_call_job
            if kind == "ai_call"
            else task,
            wid,
            pk,
        )
    for workspace_id, pk in ConversationState.all_objects.filter(
        status="running", available_at__lte=timezone.now()
    ).values_list("workspace_id", "pk")[:100]:
        enqueue_once(step, workspace_id, pk)
    for workspace_id, pk in ConversationState.all_objects.filter(
        status="waiting", timeout_at__lte=timezone.now()
    ).values_list("workspace_id", "pk")[:100]:
        enqueue_once(wait_timed_out, workspace_id, pk)
    from .intents import recover_stuck
    from .models import IntentMatch

    recover_stuck()
    for workspace_id, pk in IntentMatch.all_objects.filter(
        status="pending", available_at__lte=timezone.now()
    ).values_list("workspace_id", "pk")[:100]:
        enqueue_once(process_intent_match, workspace_id, pk)


@shared_task(ignore_result=True, soft_time_limit=60, time_limit=90)
@pause_guard("automations", "ai")
def process_intent_match(workspace_id, job_id):
    from .intents import execute_intent_match

    execute_intent_match(workspace_id, job_id)


@shared_task(ignore_result=True)
@pause_guard("automations")
def wait_timed_out(workspace_id, state_id):
    """No reply arrived in time: continue down the wait step's "timeout" path."""
    with transaction.atomic():
        state = (
            ConversationState.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=state_id, status="waiting", timeout_at__lte=timezone.now())
            .first()
        )
        if not state:
            return
        target = next(
            (
                e["target"]
                for e in state.graph["edges"]
                if e["source"] == state.node_id and e.get("sourceHandle") == "timeout"
            ),
            None,
        )
        state.timeout_at = None
        if target is None:
            state.status = "failed"
            state.error_code = "invalid_transition_or_delivery_guard"
        else:
            state.node_id = target
            state.variables["timed_out"] = True
            state.status = "running"
            state.available_at = timezone.now()
            state.steps += 1
        state.save()
        if state.status == "running":
            transaction.on_commit(lambda: release(step, state_id))


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
            if kind in {"wait", "capture_email"}:
                state.status = "waiting"
                timeout = data.get("timeout_seconds") if kind == "wait" else None
                state.timeout_at = (
                    timezone.now() + timedelta(seconds=int(timeout)) if timeout else None
                )
                state.save()
                return
            if kind == "start_agent":
                from .actions import start_agent

                start_agent(state)
                state.status = "completed"
                state.save()
                return
            if kind == "avatar_video":
                from .avatar import avatar_step

                if not avatar_step(state, data):
                    return
            if kind == "ai_call":
                from .calls import call_step

                if not call_step(state, data):
                    return
            if kind == "generate_voice":
                from .media_steps import voice_step

                if not voice_step(state, data):
                    return
            if kind == "integration_action":
                from .actions import integration_step

                if not integration_step(state, data):
                    return
            if kind == "transfer":
                from .models import Automation

                target = (
                    Automation.objects.for_workspace(workspace_id)
                    .filter(pk=data["automation_id"], enabled=True)
                    .exclude(published={})
                    .first()
                )
                if not target:
                    raise ValidationError("The destination automation is unavailable.")
                target_connection = target.published.get("connection_id")
                if target_connection and str(target_connection) != str(
                    state.conversation.identity.connection_id
                ):
                    raise ValidationError("The destination automation belongs to another account.")
                if any(
                    t.get("channel")
                    and t["channel"] != state.conversation.identity.connection.provider
                    for t in target.published["triggers"]
                ):
                    raise ValidationError("The destination automation uses a different channel.")
                # Keep the execution budget and opt-in state across transfers to bound cycles.
                state.automation = target
                state.graph = target.published
                state.node_id = target.published["start"]
                state.steps += 1
                state.save()
                transaction.on_commit(lambda: release(step, state_id))
                return
            if kind == "ai_agent":
                from .agent_step import DEFAULT_TURNS, agent_step

                outcome = agent_step(state, data)
                if outcome is None:
                    return
                result, turns = outcome
                from .agent_step import save_captured

                save_captured(state, result.get("captured") or {})
                if result["reply"]:
                    queue_reply(
                        state.conversation,
                        result["reply"],
                        f"flow:{state.id}:{state.last_message_id}:{state.steps}",
                        private_reply_id=state.variables.get("comment_id"),
                        automation_id=state.automation_id,
                    )
                    state.variables.pop("comment_id", None)
                if not result["done"] and turns < int(data.get("max_turns", DEFAULT_TURNS)):
                    # Wait for the customer's next message on this same step.
                    state.status = "waiting"
                    state.steps += 1
                    state.save()
                    return
                state.variables["agent_done"] = result["done"]
            branch = ""
            if kind == "follow_gate":
                from .followers import follow_step

                if not follow_step(state, data):
                    return
            elif kind in {"ai_generate", "ai_extract", "ai_condition"}:
                from .ai_steps import ai_step

                result = ai_step(state, data)
                if result is None:
                    return
                if kind == "ai_condition":
                    branch = result
            elif kind == "send_media":
                from apps.crm.models import Message

                if (
                    Message.objects.for_workspace(workspace_id)
                    .filter(pk=state.last_message_id, kind__in=["comment", "live_comment"])
                    .exists()
                ):
                    raise ValidationError("Wait for a private customer reply before sending media.")
                queue_reply(
                    state.conversation,
                    "",
                    f"flow:{state.id}:{state.last_message_id}:{state.steps}",
                    media_url=data["media_url"],
                    media_type=data["media_type"],
                    automation_id=state.automation_id,
                )
            elif kind in {"send_message", "send_buttons", "send_reminder"}:
                text = data["text"]
                for key, value in state.variables.items():
                    text = text.replace("{{" + key + "}}", str(value)[:2000])
                buttons = data.get("buttons")
                unless_clicked = None
                should_send = True
                if data.get("track_clicks"):
                    from .tracking import tracked_buttons

                    buttons = tracked_buttons(state, buttons)
                if kind == "send_reminder":
                    from apps.crm.models import Message

                    from .models import WorkflowLink
                    from .tracking import clicked

                    unless_clicked = {
                        "run_token": str(state.run_token),
                        "source_node": data["source_node"],
                        "conversation_id": str(state.conversation_id),
                    }
                    links = WorkflowLink.objects.for_workspace(workspace_id).filter(
                        run_token=state.run_token,
                        source_node=data["source_node"],
                        conversation_id=state.conversation_id,
                    )
                    if not links.exists():
                        raise ValidationError("No tracked resource was sent for this reminder.")
                    should_send = not clicked(workspace_id, unless_clicked)
                    if (
                        should_send
                        and Message.objects.for_workspace(workspace_id)
                        .filter(pk=state.last_message_id, kind__in=["comment", "live_comment"])
                        .exists()
                    ):
                        raise ValidationError("Wait for a private reply before sending a reminder.")
                if should_send:
                    queue_reply(
                        state.conversation,
                        text,
                        f"flow:{state.id}:{state.last_message_id}:{state.steps}",
                        buttons=buttons,
                        unless_clicked=unless_clicked,
                        private_reply_id=state.variables.get("comment_id"),
                        automation_id=state.automation_id,
                    )
                state.variables.pop("comment_id", None)
            elif kind == "delay":
                from .services import delay_seconds

                state.available_at = timezone.now() + timedelta(seconds=delay_seconds(state, data))
            elif kind in {"add_tag", "assign_member", "set_field", "set_stage"}:
                from .guided import apply_action

                apply_action(state, data)
            elif kind == "randomizer":
                seed = f"{state.id}:{state.automation_id}:{state.node_id}:{state.last_message_id}"
                bucket = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % 100
                branch = "true" if bucket < data.get("percentage", 50) else "false"
            elif kind in {"condition", "branch"}:
                from .conditions import context_for, evaluate

                branch = "true" if evaluate(data, context_for(state)) else "false"
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


@shared_task(ignore_result=True)
@pause_guard("automations", "ai")
def process_ai_job(workspace_id, job_id):
    from .ai_steps import execute_ai

    execute_ai(workspace_id, job_id)


@shared_task(ignore_result=True)
@pause_guard("automations")
def process_follow_job(workspace_id, job_id):
    from .followers import execute_follow_check

    execute_follow_check(workspace_id, job_id)


@shared_task(ignore_result=True)
@pause_guard("automations", "ai")
def process_voice_job(workspace_id, job_id):
    from .media_steps import execute_voice

    execute_voice(workspace_id, job_id)


@shared_task(ignore_result=True)
@pause_guard("automations", "ai")
def process_call_job(workspace_id, job_id):
    from .calls import execute_call

    execute_call(workspace_id, job_id)


@shared_task(ignore_result=True)
@pause_guard("automations", "ai")
def process_avatar_job(workspace_id, job_id):
    from .avatar import execute_avatar

    execute_avatar(workspace_id, job_id)
