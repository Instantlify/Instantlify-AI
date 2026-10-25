"""Create a HeyGen v3 video once, poll safely, then queue a guarded private delivery."""

import json
import re
import uuid
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.channels.transport import ProviderError, RetryableError


def validate_avatar(data):
    if data["kind"] != "avatar_video":
        return
    try:
        uuid.UUID(str(data.get("integration_id", "")))
    except ValueError:
        raise ValidationError("Choose a connected HeyGen integration.") from None
    if not isinstance(data.get("text"), str) or not 1 <= len(data["text"].strip()) <= 2000:
        raise ValidationError("An avatar script needs 1–2000 characters.")
    for field in ["avatar_id", "voice_id"]:
        if field in data and (
            not isinstance(data[field], str)
            or (data[field] and not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", data[field]))
        ):
            raise ValidationError("Use valid provider avatar and voice IDs.")
    if data.get("aspect_ratio", "auto") not in {"auto", "16:9", "9:16", "1:1"}:
        raise ValidationError("Choose a supported video aspect ratio.")


def avatar_config(workspace_id, data):
    from apps.billing.gating import PlanLimitExceeded, check_feature
    from apps.crm.models import IntegrationConfig
    from apps.platform_ops.security import blocked

    try:
        check_feature(workspace_id, "integrations_unlocked")
        check_feature(workspace_id, "ai_agent_enabled")
    except PlanLimitExceeded:
        raise ValidationError(
            "The workspace plan does not include avatar video integrations."
        ) from None
    config = (
        IntegrationConfig.objects.for_workspace(workspace_id)
        .filter(pk=data["integration_id"], provider="heygen", enabled=True, status="active")
        .first()
    )
    if not config or blocked(workspace_id, "ai", "integration:heygen"):
        raise ValidationError("Choose an active HeyGen integration.")
    if config.is_test:
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise ValidationError("Local avatar tests are disabled in live mode.")
        return config
    credentials = json.loads(config.credentials)
    if not isinstance(credentials.get("api_key"), str) or not credentials["api_key"].strip():
        raise ValidationError("Save your HeyGen API key.")
    for field in ["avatar_id", "voice_id"]:
        value = data.get(field) or config.options.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value):
            raise ValidationError("Save a Digital Twin avatar look ID and voice ID from HeyGen.")
    return config


def avatar_step(state, data):
    from apps.crm.models import Message

    from .models import WorkflowActionJob

    avatar_config(state.workspace_id, data)
    if (
        Message.objects.for_workspace(state.workspace_id)
        .filter(pk=state.last_message_id, kind__in=["comment", "live_comment"])
        .exists()
    ):
        raise ValidationError("Wait for a private reply before generating an avatar video.")
    text = data["text"]
    for name, value in state.variables.items():
        text = text.replace("{{" + name + "}}", str(value)[:2000])
    if len(text) > 2000:
        raise ValidationError("The rendered avatar script exceeds 2000 characters.")
    job, _ = WorkflowActionJob.objects.for_workspace(state.workspace_id).get_or_create(
        key=f"avatar:{state.run_token}:{state.node_id}:{state.steps}",
        defaults={
            "workspace_id": state.workspace_id,
            "state": state,
            "kind": "avatar_video",
            "payload": json.dumps({**data, "text": text, "run_token": str(state.run_token)}),
            "available_at": timezone.now(),
        },
    )
    if job.status in {"pending", "executing", "rendering", "polling"}:
        state.available_at = max(job.available_at, timezone.now() + timedelta(seconds=10))
        state.save()
        return False
    if job.status != "complete":
        raise ValidationError(
            "This avatar generation needs review; it will not be recreated automatically."
        )
    return True


def create_video(config, data):
    from apps.channels.transport import request

    result = request(
        "POST",
        "https://api.heygen.com/v3/videos",
        headers={"X-Api-Key": json.loads(config.credentials)["api_key"]},
        side_effect=True,
        json={
            "type": "avatar",
            "avatar_id": data.get("avatar_id") or config.options["avatar_id"],
            "voice_id": data.get("voice_id") or config.options["voice_id"],
            "script": data["text"],
            "aspect_ratio": data.get("aspect_ratio", "auto"),
            "resolution": "720p",
        },
    )
    identifier = result.get("data", {}).get("video_id") or result.get("data", {}).get("id")
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", identifier):
        raise ProviderError("avatar_result_unknown")
    return identifier


def execute_avatar(workspace_id, job_id):
    from apps.channels.media import validate_media
    from apps.channels.transport import request
    from apps.crm.services import queue_reply, window_closed
    from apps.platform_ops.security import blocked
    from apps.tenants.services import audit

    from .models import WorkflowActionJob

    with transaction.atomic():
        job = (
            WorkflowActionJob.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(
                pk=job_id,
                kind="avatar_video",
                status__in=["pending", "rendering"],
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
        if blocked(workspace_id, "automations", "ai", f"automation:{state.automation_id}"):
            return
        try:
            data = json.loads(job.payload)
            config = avatar_config(workspace_id, data)
            connection = state.conversation.identity.connection
            if (
                state.status != "running"
                or str(state.run_token) != data["run_token"]
                or state.conversation.identity.lead.opted_out
                or window_closed(connection, state.conversation)
                or job.created_at < timezone.now() - timedelta(minutes=30)
            ):
                raise ValidationError("Avatar rendering or delivery context expired.")
            if connection.is_test and not config.is_test:
                raise ValidationError("Use a test HeyGen integration with a test channel.")
        except Exception:
            job.status, job.error_code = "needs_review", "avatar_context_unavailable"
            job.save()
            return
        creating = job.status == "pending"
        job.status, job.available_at = "executing" if creating else "polling", timezone.now()
        job.save()
    try:
        if config.is_test:
            delivery = queue_reply(
                state.conversation,
                "[Local avatar test] " + data["text"],
                f"workflow-avatar:{job.pk}",
            )
            job.status, job.result = (
                "complete",
                json.dumps({"delivery_id": str(delivery.pk), "test": True}),
            )
        elif creating:
            identifier = create_video(config, data)
            job.status, job.result = "rendering", json.dumps({"video_id": identifier})
            job.available_at = timezone.now() + timedelta(seconds=30)
        else:
            identifier = json.loads(job.result)["video_id"]
            result = request(
                "GET",
                "https://api.heygen.com/v3/videos/" + quote(identifier, safe=""),
                headers={"X-Api-Key": json.loads(config.credentials)["api_key"]},
            ).get("data", {})
            status = result.get("status")
            if status == "completed":
                url = result.get("video_url")
                validate_media(url, "video")
                delivery = queue_reply(
                    state.conversation,
                    "",
                    f"workflow-avatar:{job.pk}",
                    media_url=url,
                    media_type="video",
                    automation_id=state.automation_id,
                )
                job.status, job.result = (
                    "complete",
                    json.dumps({"video_id": identifier, "delivery_id": str(delivery.pk)}),
                )
            elif status in {"pending", "processing"}:
                job.status, job.available_at = "rendering", timezone.now() + timedelta(seconds=30)
            else:
                raise ProviderError("avatar_render_failed")
    except RetryableError as exc:
        if creating:
            job.status, job.error_code = "needs_review", "avatar_creation_failed_or_unknown"
        else:
            job.status, job.available_at = (
                "rendering",
                timezone.now() + timedelta(seconds=exc.delay),
            )
    except Exception:
        job.status, job.error_code = "needs_review", "avatar_failed_or_result_unknown"
    job.save()
    if job.status in {"complete", "needs_review"}:
        audit(job.workspace, None, "workflow_avatar." + job.status, job.pk)
