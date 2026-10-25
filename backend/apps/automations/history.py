from django.utils import timezone

from .models import AutomationExecution

TERMINAL = {"completed", "failed", "stopped", "needs_review", "superseded"}


def record_state(state):
    """Store transition metadata only, never prompts, replies, tokens or variables."""
    run, _ = AutomationExecution.objects.for_workspace(state.workspace_id).get_or_create(
        pk=state.run_token,
        defaults={
            "workspace_id": state.workspace_id,
            "conversation_id": state.conversation_id,
            "automation_id": state.automation_id,
            "automation_name": state.automation.name,
            "revision": state.automation.revision,
            "status": state.status,
            "node_id": state.node_id,
        },
    )
    run = (
        AutomationExecution.objects.for_workspace(state.workspace_id)
        .select_for_update()
        .get(pk=run.pk)
    )
    event = {"node_id": state.node_id, "steps": state.steps, "status": state.status}
    previous = {key: run.trace[-1].get(key) for key in event} if run.trace else None
    if previous != event:
        run.trace = [*run.trace[-199:], {**event, "at": timezone.now().isoformat()}]
    run.status = state.status
    run.steps = state.steps
    run.node_id = state.node_id
    run.error_code = state.error_code
    run.finished_at = (run.finished_at or timezone.now()) if state.status in TERMINAL else None
    run.save()
