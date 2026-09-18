import base64
import json
from urllib.parse import quote, urlparse

import httpx
from django.conf import settings
from django.core import signing
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from apps.channels.transport import ProviderError, request
from apps.crm.models import IntegrationConfig
from apps.crm.services import queue_reply

from .models import VoiceAsset


def bounded_bytes(method, url, **kwargs):
    try:
        with httpx.stream(method, url, timeout=30, follow_redirects=False, **kwargs) as response:
            if not response.is_success:
                raise ProviderError("media_provider_rejected")
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 10 * 1024 * 1024:
                    raise ProviderError("media_size_limit")
            return bytes(data)
    except httpx.HTTPError:
        raise ProviderError("media_transport_failed") from None


def queue_voice(conversation, text, key):
    from apps.platform_ops.security import assert_enabled

    assert_enabled(conversation.workspace_id, "ai", "integration:elevenlabs")
    integration = (
        IntegrationConfig.objects.for_workspace(conversation.workspace_id)
        .filter(provider="elevenlabs", enabled=True)
        .first()
    )
    if not integration:
        raise ValueError("voice_not_configured")
    if integration.is_test:
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise ValueError("test_voice_disabled")
        item = queue_reply(conversation, "[Local voice test] " + text, f"voice:{key}")
        return {"delivery_id": str(item.id), "test": True}
    credentials = json.loads(integration.credentials)
    audio = bounded_bytes(
        "POST",
        f"https://api.elevenlabs.io/v1/text-to-speech/{quote(integration.options['voice_id'], safe='')}",
        headers={"xi-api-key": credentials["api_key"]},
        json={
            "text": text[:2000],
            "model_id": integration.options.get("model", "eleven_multilingual_v2"),
        },
    )
    asset = VoiceAsset.objects.for_workspace(conversation.workspace_id).create(
        workspace_id=conversation.workspace_id, audio=base64.b64encode(audio).decode()
    )
    token = signing.dumps(
        {"workspace": str(conversation.workspace_id), "asset": str(asset.id)}, salt="voice"
    )
    url = settings.PUBLIC_APP_URL + "/media/voice/" + token + "/"
    if not url.startswith("https://"):
        raise ValueError("public_https_required")
    item = queue_reply(conversation, text, f"voice:{key}", media_url=url)
    return {"delivery_id": str(item.id)}


def voice_asset(request, token):
    try:
        data = signing.loads(token, salt="voice", max_age=3600)
    except signing.BadSignature:
        return HttpResponse(status=403)
    asset = get_object_or_404(VoiceAsset.objects.for_workspace(data["workspace"]), pk=data["asset"])
    response = HttpResponse(base64.b64decode(asset.audio), content_type=asset.content_type)
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


TRANSCRIPTION_MODEL = "whisper-1"


def transcribe(message, config):
    """Return (transcript, audio seconds) for the message's voice attachment; ("", 0) if
    it has none. The duration is Whisper's own measurement, which is what it bills."""
    attachments = json.loads(message.attachments)
    attachment = next(
        (a for a in attachments if isinstance(a, dict) and a.get("type") in {"audio", "voice"}),
        None,
    )
    if not attachment:
        return "", 0.0
    connection = message.conversation.identity.connection
    if connection.is_test or config.is_test:
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise ProviderError("test_transcription_disabled")
        return (
            str(attachment.get("transcript", "[Local test voice note]")),
            float(attachment.get("duration", 5)),
        )
    filename = "voice.ogg"
    if connection.provider == "telegram":
        from apps.channels.providers import TelegramAdapter

        file = TelegramAdapter(connection).call("getFile", {"file_id": attachment["media_id"]})
        url = f"https://api.telegram.org/file/bot{connection.access_token}/{file['file_path']}"
        headers = {}
    elif connection.provider == "whatsapp":
        media = request(
            "GET",
            f"https://graph.facebook.com/{settings.META_API_VERSION}/{quote(attachment['media_id'], safe='')}",
            headers={"Authorization": f"Bearer {connection.access_token}"},
        )
        url = media["url"]
        headers = {"Authorization": f"Bearer {connection.access_token}"}
    else:
        url = attachment.get("payload", {}).get("url", "")
        headers = {}
        filename = "voice.mp4"
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not any(
            parsed.hostname == domain or parsed.hostname.endswith("." + domain)
            for domain in [
                "cdninstagram.com",
                "fbcdn.net",
                "fbsbx.com",
                "facebook.com",
                "api.telegram.org",
            ]
        )
    ):
        raise ProviderError("untrusted_media_url")
    audio = bounded_bytes("GET", url, headers=headers)
    result = request(
        "POST",
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {config.api_key}"},
        data={"model": TRANSCRIPTION_MODEL, "response_format": "verbose_json"},
        files={"file": (filename, audio, "application/octet-stream")},
    )
    return str(result.get("text", "")), float(result.get("duration") or 0)
