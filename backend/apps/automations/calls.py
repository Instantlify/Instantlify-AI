"""One-shot, consent-bound outbound calls scheduled in the workspace's chosen zone."""

import json
import re
import uuid
from datetime import UTC, datetime, time, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

PHONE = re.compile(r"\+[1-9][0-9]{7,14}\Z")


def validate_call(data):
    if data["kind"] != "ai_call":
        return
    if type(data.get("wait_for_completion", False)) is not bool:
        raise ValidationError("Choose whether to wait for the call outcome.")
    try:
        uuid.UUID(str(data.get("integration_id", "")))
        zone = data.get("timezone", "UTC")
        if not isinstance(zone, str):
            raise ValueError
        ZoneInfo(zone)
        start = time.fromisoformat(data.get("call_start", "09:00"))
        end = time.fromisoformat(data.get("call_end", "18:00"))
        if start.tzinfo or end.tzinfo or start >= end:
            raise ValueError
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise ValidationError(
            "Choose an integration, IANA timezone and a same-day calling window."
        ) from None
    days = data.get("weekdays", [0, 1, 2, 3, 4])
    if (
        not isinstance(days, list)
        or not days
        or len(days) > 7
        or any(type(day) is not int or not 0 <= day <= 6 for day in days)
    ):
        raise ValidationError("Choose at least one allowed weekday.")
    for field in ["phone_variable", "variable"]:
        if (
            not isinstance(
                data.get(field, "phone" if field == "phone_variable" else "call_result"), str
            )
            or not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]{0,59}",
                data.get(field, "phone" if field == "phone_variable" else "call_result"),
            )
            or data.get(field) in {"comment_id", "last_text"}
        ):
            raise ValidationError("Use a short, non-reserved variable name.")
    reply = data.get("consent_reply")
    if not isinstance(reply, str) or not 1 <= len(reply.strip()) <= 64:
        raise ValidationError("Set the exact private reply that requests a phone call.")
    agent = data.get("agent_id", "")
    if not isinstance(agent, str) or (agent and not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", agent)):
        raise ValidationError("Choose a valid saved provider agent ID.")


def next_call_time(data, now):
    zone = ZoneInfo(data.get("timezone", "UTC"))
    local = now.astimezone(zone)
    for offset in range(8):
        day = local.date() + timedelta(days=offset)
        if day.weekday() not in data.get("weekdays", [0, 1, 2, 3, 4]):
            continue
        start = datetime.combine(day, time.fromisoformat(data.get("call_start", "09:00")), zone)
        end = datetime.combine(day, time.fromisoformat(data.get("call_end", "18:00")), zone)
        candidate = max(start, local).astimezone(UTC)
        # A DST transition must still land inside the chosen local window.
        wall = candidate.astimezone(zone)
        if start <= wall < end:
            return candidate
    raise ValidationError("No permitted calling time was found.")


def call_config(workspace_id, data):
    from apps.billing.gating import PlanLimitExceeded, check_feature
    from apps.crm.models import IntegrationConfig
    from apps.platform_ops.security import blocked

    try:
        check_feature(workspace_id, "integrations_unlocked")
        check_feature(workspace_id, "ai_agent_enabled")
    except PlanLimitExceeded:
        raise ValidationError(
            "The workspace plan does not include AI calling integrations."
        ) from None
    config = (
        IntegrationConfig.objects.for_workspace(workspace_id)
        .filter(
            pk=data["integration_id"],
            provider__in=["vapi", "retell"],
            enabled=True,
            status="active",
        )
        .first()
    )
    if not config or blocked(workspace_id, "ai", "integration:" + config.provider):
        raise ValidationError("Choose an active Vapi or Retell integration.")
    if config.is_test:
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise ValidationError("Test calls are disabled in live mode.")
        return config
    credentials = json.loads(config.credentials)
    if not isinstance(credentials.get("api_key"), str) or not credentials["api_key"].strip():
        raise ValidationError("Save your calling provider API key.")
    agent = data.get("agent_id") or config.options.get("agent_id")
    if not isinstance(agent, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", agent):
        raise ValidationError("Save a provider agent ID in the integration or call step.")
    if config.provider == "retell":
        if not isinstance(config.options.get("from_number"), str) or not PHONE.fullmatch(
            config.options["from_number"]
        ):
            raise ValidationError(
                "Save your Retell caller number in international +country format."
            )
    else:
        try:
            uuid.UUID(str(config.options.get("phone_number_id", "")))
            uuid.UUID(agent)
        except ValueError:
            raise ValidationError("Vapi requires valid phone number and assistant UUIDs.") from None
    return config


def consent_message(state, message_id, phrase):
    from apps.crm.models import Message

    message = (
        Message.objects.for_workspace(state.workspace_id)
        .filter(
            pk=message_id,
            conversation_id=state.conversation_id,
            direction="inbound",
            created_at__gte=timezone.now() - timedelta(days=7),
        )
        .exclude(kind__in=["comment", "live_comment"])
        .first()
    )
    if not message or message.text.strip().casefold() != phrase.strip().casefold():
        raise ValidationError(
            "The customer must privately send the configured call request before this step."
        )
    return message


def call_step(state, data):
    from .models import WorkflowActionJob

    call_config(state.workspace_id, data)
    consent = consent_message(state, state.last_message_id, data["consent_reply"])
    phone = state.variables.get(data.get("phone_variable", "phone"))
    if not isinstance(phone, str) or not PHONE.fullmatch(phone):
        raise ValidationError("Capture a phone number in international +country format first.")
    due = next_call_time(data, timezone.now())
    job, _ = WorkflowActionJob.objects.for_workspace(state.workspace_id).get_or_create(
        key=f"call:{state.run_token}:{state.node_id}:{state.steps}",
        defaults={
            "workspace_id": state.workspace_id,
            "state": state,
            "kind": "ai_call",
            "payload": json.dumps(
                {
                    **data,
                    "phone": phone,
                    "consent_message_id": str(consent.pk),
                    "run_token": str(state.run_token),
                }
            ),
            "available_at": due,
        },
    )
    if job.status in {"pending", "executing", "calling", "call_polling"}:
        state.available_at = max(job.available_at, timezone.now() + timedelta(seconds=10))
        state.save()
        return False
    if job.status != "complete":
        raise ValidationError("The call needs review; it will not be repeated automatically.")
    state.variables[data.get("variable", "call_result")] = json.loads(job.result)
    return True


def create_call(config, data, key):
    from apps.channels.transport import ProviderError, request

    if config.is_test:
        return {"id": "test-call-" + key, "status": "simulated", "test": True}
    headers = {"Authorization": "Bearer " + json.loads(config.credentials)["api_key"]}
    agent = data.get("agent_id") or config.options["agent_id"]
    if config.provider == "vapi":
        result = request(
            "POST",
            "https://api.vapi.ai/call",
            headers=headers,
            side_effect=True,
            json={
                "assistantId": agent,
                "phoneNumberId": config.options["phone_number_id"],
                "customer": {"number": data["phone"]},
            },
        )
        identifier = result.get("id")
    else:
        result = request(
            "POST",
            "https://api.retellai.com/v2/create-phone-call",
            headers=headers,
            side_effect=True,
            json={
                "from_number": config.options["from_number"],
                "to_number": data["phone"],
                "override_agent_id": agent,
                "idempotency_key": key,
            },
        )
        identifier = result.get("call_id")
    if not isinstance(identifier, str) or not identifier or len(identifier) > 200:
        raise ProviderError("call_result_unknown")
    return {"id": identifier, "status": "accepted", "test": False}


def call_outcome(config, identifier):
    from apps.channels.transport import ProviderError, request

    if config.is_test:
        return {
            "id": identifier,
            "status": "ended",
            "summary": "Local test call completed.",
            "test": True,
        }
    url = (
        "https://api.vapi.ai/call/"
        if config.provider == "vapi"
        else "https://api.retellai.com/v2/get-call/"
    ) + quote(identifier, safe="")
    body = request(
        "GET", url, headers={"Authorization": "Bearer " + json.loads(config.credentials)["api_key"]}
    )
    if (body.get("id") if config.provider == "vapi" else body.get("call_id")) != identifier:
        raise ProviderError("call_result_mismatch")
    status = body.get("status") if config.provider == "vapi" else body.get("call_status")
    if status not in {
        "queued",
        "scheduled",
        "ringing",
        "in-progress",
        "forwarding",
        "registered",
        "not_connected",
        "ongoing",
        "ended",
        "error",
    }:
        raise ProviderError("call_status_unknown")
    analysis = body.get("analysis") if config.provider == "vapi" else body.get("call_analysis")
    analysis = analysis if isinstance(analysis, dict) else {}
    summary = analysis.get("summary", analysis.get("call_summary", ""))
    return {
        "id": identifier,
        "status": status,
        "summary": str(summary or "")[:4000],
        "ended_reason": str(body.get("endedReason", body.get("disconnection_reason", "")) or "")[
            :150
        ],
        "test": False,
    }


def execute_call(workspace_id, job_id):
    from apps.platform_ops.security import blocked
    from apps.tenants.services import audit

    from .models import WorkflowActionJob

    with transaction.atomic():
        job = (
            WorkflowActionJob.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(
                pk=job_id,
                kind="ai_call",
                status__in=["pending", "calling"],
                available_at__lte=timezone.now(),
            )
            .select_related(
                "state__conversation__identity__lead", "state__conversation__identity__connection"
            )
            .first()
        )
        if not job:
            return
        state = job.state
        polling = job.status == "calling"
        if blocked(workspace_id, "automations", "ai", f"automation:{state.automation_id}"):
            return
        try:
            data = json.loads(job.payload)
            if (
                state.status != "running"
                or str(state.run_token) != data["run_token"]
                or state.conversation.identity.lead.opted_out
            ):
                raise ValidationError("The call context is no longer available.")
            config = call_config(workspace_id, data)
            if not polling:
                consent_message(state, data["consent_message_id"], data["consent_reply"])
            if state.conversation.identity.connection.is_test and not config.is_test:
                raise ValidationError("Use a test calling integration with a test channel.")
            due = timezone.now() if polling else next_call_time(data, timezone.now())
            if due > timezone.now() + timedelta(seconds=1):
                job.available_at = due
                job.save()
                return
        except Exception:
            job.status, job.error_code = "needs_review", "call_context_unavailable"
            job.save()
            return
        job.status, job.available_at = "call_polling" if polling else "executing", timezone.now()
        job.save()
    try:
        if polling:
            from django.utils.dateparse import parse_datetime

            previous = json.loads(job.result)
            accepted = parse_datetime(previous["accepted_at"])
            if not accepted or timezone.now() - accepted > timedelta(hours=2):
                raise ValidationError("The call outcome timed out.")
            result = {
                **call_outcome(config, previous["id"]),
                "accepted_at": previous["accepted_at"],
            }
            job.status = (
                "complete" if result["status"] in {"ended", "error", "not_connected"} else "calling"
            )
        else:
            result = create_call(config, data, str(job.pk))
            result["accepted_at"] = timezone.now().isoformat()
            job.status = "calling" if data.get("wait_for_completion") else "complete"
        job.result = json.dumps(result)
        if job.status == "calling":
            job.available_at = timezone.now() + timedelta(seconds=30)
    except Exception:
        if polling:
            # Polling is read-only: a transient fetch may be retried without another call.
            job.status = "calling"
            job.available_at = timezone.now() + timedelta(seconds=60)
            from django.utils.dateparse import parse_datetime

            accepted = parse_datetime(json.loads(job.result).get("accepted_at", ""))
            if not accepted or timezone.now() - accepted > timedelta(hours=2):
                job.status, job.error_code = "needs_review", "call_outcome_timeout"
        else:
            job.status, job.error_code = "needs_review", "call_failed_or_result_unknown"
    job.save()
    audit(job.workspace, None, "workflow_call." + job.status, job.pk)
