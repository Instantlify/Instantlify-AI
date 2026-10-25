"""Durable voice generation with tenant-owned provider credentials."""

import base64
import json
import uuid
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.channels.transport import ProviderError

VOICE_PROVIDERS = {"elevenlabs", "inworld", "minimax"}


def validate_voice(data):
    if data["kind"] != "generate_voice":
        return
    try:
        uuid.UUID(str(data.get("integration_id", "")))
    except ValueError:
        raise ValidationError("Choose a connected voice integration.") from None
    if not isinstance(data.get("text"), str) or not 1 <= len(data["text"].strip()) <= 2000:
        raise ValidationError("Voice text needs 1–2000 characters.")


def voice_config(workspace_id, integration_id):
    from apps.billing.gating import PlanLimitExceeded, check_feature
    from apps.crm.models import IntegrationConfig
    from apps.platform_ops.security import blocked

    try:
        check_feature(workspace_id, "voice_notes_enabled")
        check_feature(workspace_id, "integrations_unlocked")
    except PlanLimitExceeded:
        raise ValidationError(
            "The workspace plan does not include generated voice integrations."
        ) from None
    config = (
        IntegrationConfig.objects.for_workspace(workspace_id)
        .filter(pk=integration_id, enabled=True, status="active", provider__in=VOICE_PROVIDERS)
        .first()
    )
    if not config:
        raise ValidationError("Choose an active ElevenLabs, Inworld or MiniMax integration.")
    if blocked(workspace_id, "ai", "integration:" + config.provider):
        raise ValidationError("This voice provider is paused.")
    if config.is_test:
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise ValidationError("Test voice integrations are disabled in live mode.")
        return config
    credentials = json.loads(config.credentials)
    if (
        any(
            not isinstance(value, str) or not value.strip() or "\r" in value or "\n" in value
            for value in [credentials.get("api_key"), config.options.get("voice_id")]
        )
        or (config.provider != "elevenlabs" and not config.options.get("model"))
        or not isinstance(config.options.get("model", ""), str)
    ):
        raise ValidationError(
            "Save an API key, voice ID and provider model in the voice integration."
        )
    return config


def voice_step(state, data):
    from apps.crm.models import Message

    from .models import WorkflowActionJob

    voice_config(state.workspace_id, data["integration_id"])
    if (
        Message.objects.for_workspace(state.workspace_id)
        .filter(pk=state.last_message_id, kind__in=["comment", "live_comment"])
        .exists()
    ):
        raise ValidationError("Wait for a private reply before sending generated voice.")
    text = data["text"]
    for key, value in state.variables.items():
        text = text.replace("{{" + key + "}}", str(value)[:2000])
    if len(text.encode("utf-16-le")) // 2 > 2000:
        raise ValidationError("The rendered voice text exceeds 2000 characters.")
    job, _ = WorkflowActionJob.objects.for_workspace(state.workspace_id).get_or_create(
        key=f"voice:{state.run_token}:{state.node_id}:{state.steps}",
        defaults={
            "workspace_id": state.workspace_id,
            "state": state,
            "kind": "generate_voice",
            "payload": json.dumps(
                {
                    "integration_id": data["integration_id"],
                    "text": text,
                    "run_token": str(state.run_token),
                }
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
            "Voice generation needs review. It will not be repeated automatically."
        )
    return True


def synthesize(config, text):
    from apps.agents.voice import bounded_bytes

    credentials = json.loads(config.credentials)
    voice = config.options["voice_id"]
    model = config.options.get("model") or "eleven_multilingual_v2"
    if config.provider == "elevenlabs":
        audio = bounded_bytes(
            "POST",
            f"https://api.elevenlabs.io/v1/text-to-speech/{quote(voice, safe='')}",
            headers={"xi-api-key": credentials["api_key"]},
            json={"text": text, "model_id": model},
        )
    elif config.provider == "inworld":
        result = json.loads(
            bounded_bytes(
                "POST",
                "https://api.inworld.ai/tts/v1/voice",
                headers={"Authorization": "Basic " + credentials["api_key"]},
                json={
                    "text": text,
                    "voiceId": voice,
                    "modelId": model,
                    "audioConfig": {"audioEncoding": "MP3"},
                },
            )
        )
        audio = base64.b64decode(result["audioContent"], validate=True)
    else:
        result = json.loads(
            bounded_bytes(
                "POST",
                "https://api.minimax.io/v1/t2a_v2",
                headers={"Authorization": "Bearer " + credentials["api_key"]},
                json={
                    "model": model,
                    "text": text,
                    "stream": False,
                    "output_format": "hex",
                    "voice_setting": {"voice_id": voice},
                    "audio_setting": {"format": "mp3"},
                },
            )
        )
        if result.get("base_resp", {}).get("status_code") != 0:
            raise ProviderError("voice_provider_rejected")
        audio = bytes.fromhex(result["data"]["audio"])
    if not audio or len(audio) > 10 * 1024 * 1024:
        raise ProviderError("voice_size_limit")
    return audio


def execute_voice(workspace_id, job_id):
    from apps.agents.models import VoiceAsset
    from apps.crm.services import queue_reply, window_closed
    from apps.platform_ops.security import blocked
    from apps.tenants.services import audit

    from .models import WorkflowActionJob

    with transaction.atomic():
        job = (
            WorkflowActionJob.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=job_id, kind="generate_voice", status="pending")
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
            config = voice_config(workspace_id, data["integration_id"])
            connection = state.conversation.identity.connection
            if (
                state.status != "running"
                or str(state.run_token) != data["run_token"]
                or state.conversation.identity.lead.opted_out
                or window_closed(connection, state.conversation)
            ):
                raise ValidationError("Voice delivery context is no longer available.")
            if connection.is_test and not config.is_test:
                raise ValidationError("A test channel requires a test voice integration.")
            if not config.is_test and not settings.PUBLIC_APP_URL.startswith("https://"):
                raise ValidationError("Generated voice requires a public HTTPS app URL.")
        except Exception:
            job.status, job.error_code = "needs_review", "voice_context_unavailable"
            job.save()
            return
        job.status, job.available_at = "executing", timezone.now()
        job.save()
    try:
        if config.is_test:
            delivery = queue_reply(
                state.conversation, "[Local voice test] " + data["text"], f"workflow-voice:{job.pk}"
            )
        else:
            audio = synthesize(config, data["text"])
            with transaction.atomic():
                asset = VoiceAsset.objects.for_workspace(workspace_id).create(
                    workspace_id=workspace_id, audio=base64.b64encode(audio).decode()
                )
                token = signing.dumps(
                    {"workspace": str(workspace_id), "asset": str(asset.pk)}, salt="voice"
                )
                delivery = queue_reply(
                    state.conversation,
                    data["text"],
                    f"workflow-voice:{job.pk}",
                    media_url=settings.PUBLIC_APP_URL.rstrip("/") + "/media/voice/" + token + "/",
                )
        job.status, job.result = (
            "complete",
            json.dumps({"delivery_id": str(delivery.pk), "test": config.is_test}),
        )
    except Exception:
        job.status, job.error_code = "needs_review", "voice_failed_or_result_unknown"
    job.save()
    audit(job.workspace, None, "workflow_voice." + job.status, job.pk)
