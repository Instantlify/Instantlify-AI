"""Bridge flow steps into existing durable integration and AI workers."""

import json
from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError


def integration_step(state, data):
    from apps.crm.models import IntegrationConfig, IntegrationJob
    from apps.public_api.services import lead_payload

    config = (
        IntegrationConfig.objects.for_workspace(state.workspace_id)
        .filter(pk=data["integration_id"], enabled=True, status="active")
        .first()
    )
    if not config:
        raise ValidationError("The integration is unavailable.")
    key = f"flow:{state.run_token}:{state.steps}:{state.last_message_id}:integration"
    payload = lead_payload(state.conversation.identity.lead)
    text = data.get("text", "")
    for name, value in state.variables.items():
        text = text.replace("{{" + name + "}}", str(value)[:500])
    payload.update(
        text=text[:2000],
        _flow={
            "state_id": str(state.pk),
            "automation_id": str(state.automation_id),
            "run_token": str(state.run_token),
        },
    )
    if data["operation"] == "webhook":

        def render(value):
            if isinstance(value, str):
                for name, replacement in state.variables.items():
                    value = value.replace("{{" + name + "}}", str(replacement)[:500])
                return value
            if isinstance(value, dict):
                return {key: render(item) for key, item in value.items()}
            if isinstance(value, list):
                return [render(item) for item in value]
            return value

        payload["request"] = render(json.loads(data.get("request_body", "{}")))
    if data["operation"] == "send_email":
        from django.core.exceptions import ValidationError as EmailValidationError
        from django.core.validators import validate_email

        recipient = data.get("to") or payload.get("email") or ""
        subject = data["subject"]
        for name, value in state.variables.items():
            recipient = recipient.replace("{{" + name + "}}", str(value)[:254])
            subject = subject.replace("{{" + name + "}}", str(value)[:200])
        try:
            validate_email(recipient)
        except EmailValidationError:
            raise ValidationError(
                "The contact needs a valid email address before this step."
            ) from None
        payload.update(to=recipient, subject=subject[:200])
    job, _ = IntegrationJob.objects.for_workspace(state.workspace_id).get_or_create(
        idempotency_key=key,
        defaults={
            "workspace_id": state.workspace_id,
            "integration": config,
            "operation": data["operation"],
            "payload": json.dumps(payload, default=str),
            "available_at": timezone.now(),
        },
    )
    if job.status in {"pending", "executing"}:
        state.available_at = timezone.now() + timedelta(seconds=5)
        state.save()
        return False
    if job.status != "complete":
        raise ValidationError("The integration action needs review.")
    if len(job.result) > 20000:
        raise ValidationError("The integration result is too large for a flow variable.")
    state.variables[data.get("variable", "integration_result")] = json.loads(job.result)
    if data["operation"] == "webhook":
        mapping = data.get("response_map", {})
        if isinstance(mapping, str):
            mapping = json.loads(mapping)
        for name, path in mapping.items():
            value = json.loads(job.result)
            try:
                for part in path.split("."):
                    value = value[int(part)] if isinstance(value, list) else value[part]
            except (KeyError, IndexError, TypeError, ValueError):
                raise ValidationError("A mapped response field was missing.") from None
            state.variables[name] = value
        if len(json.dumps(state.variables)) > 50000:
            raise ValidationError("Flow variables are too large.")
    return True


def start_agent(state):
    from apps.agents.models import AgentConfig, AgentRun
    from apps.billing.gating import PlanLimitExceeded, check_feature
    from apps.crm.models import Message
    from apps.tenants.services import audit

    try:
        check_feature(state.workspace_id, "ai_agent_enabled")
    except PlanLimitExceeded:
        raise ValidationError("The workspace plan no longer includes the AI assistant.") from None
    config = AgentConfig.objects.for_workspace(state.workspace_id).filter(enabled=True).first()
    message = (
        Message.objects.for_workspace(state.workspace_id)
        .filter(pk=state.last_message_id, conversation=state.conversation, direction="inbound")
        .first()
    )
    if not config or not message or message.kind in {"comment", "live_comment"}:
        raise ValidationError(
            "The assistant requires an enabled configuration and a private reply first."
        )
    state.conversation.ai_enabled = True
    state.conversation.save(update_fields=["ai_enabled", "updated_at"])
    run, created = AgentRun.objects.for_workspace(state.workspace_id).get_or_create(
        message=message, defaults={"workspace_id": state.workspace_id}
    )
    if created:
        audit(state.conversation.workspace, None, "automation.agent_started", run.pk)
