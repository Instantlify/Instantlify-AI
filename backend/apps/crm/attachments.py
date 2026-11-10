"""Inbox file attachments: validate an upload, store it, and expose a signed URL the
channel provider fetches when the media message is delivered."""

import base64

from django.conf import settings
from django.core import signing
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from .models import MessageAttachment

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
SALT = "inbox-attachment"
# Long enough for delivery retries and for the thread link to keep working.
URL_MAX_AGE = 30 * 24 * 3600


def _is_mp3(head):
    return head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)


def _is_adts(head):
    return len(head) > 1 and head[0] == 0xFF and head[1] & 0xF0 == 0xF0


# Declared type -> (media kind, magic-byte check). Only types every media channel
# (Instagram, Messenger, WhatsApp, Telegram) accepts as image, video or audio.
ALLOWED = {
    "image/jpeg": ("image", lambda b: b[:3] == b"\xff\xd8\xff"),
    "image/png": ("image", lambda b: b[:8] == b"\x89PNG\r\n\x1a\n"),
    "video/mp4": ("video", lambda b: b[4:8] == b"ftyp"),
    "audio/mpeg": ("audio", _is_mp3),
    "audio/mp4": ("audio", lambda b: b[4:8] == b"ftyp"),
    "audio/aac": ("audio", _is_adts),
    "audio/ogg": ("audio", lambda b: b[:4] == b"OggS"),
}
ALIASES = {"audio/x-m4a": "audio/mp4", "audio/mp3": "audio/mpeg", "image/jpg": "image/jpeg"}


def store_attachment(conversation, upload):
    """Validate and save an uploaded file. Returns (attachment, media_kind)."""
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    content_type = ALIASES.get(content_type, content_type)
    if content_type not in ALLOWED:
        raise ValidationError(
            "Attach a JPEG or PNG image, an MP4 video, or an MP3, M4A, AAC or OGG audio file."
        )
    if not upload.size or upload.size > MAX_ATTACHMENT_BYTES:
        raise ValidationError("Attachments must be 5 MB or smaller.")
    data = upload.read(MAX_ATTACHMENT_BYTES + 1)
    kind, looks_right = ALLOWED[content_type]
    if len(data) > MAX_ATTACHMENT_BYTES or not looks_right(data):
        raise ValidationError("The file's contents do not match its type.")
    name = "".join(ch for ch in (upload.name or "") if ch.isprintable()).strip()[:200]
    attachment = MessageAttachment.objects.for_workspace(conversation.workspace_id).create(
        workspace_id=conversation.workspace_id,
        conversation=conversation,
        filename=name or "attachment",
        content_type=content_type,
        size=len(data),
        data=base64.b64encode(data).decode(),
    )
    return attachment, kind


def attachment_url(attachment):
    token = signing.dumps(
        {"workspace": str(attachment.workspace_id), "attachment": str(attachment.pk)}, salt=SALT
    )
    return settings.PUBLIC_APP_URL.rstrip("/") + "/media/attachment/" + token + "/"


def can_deliver_by_url():
    """Providers can only fetch media from a public HTTPS origin."""
    return settings.PUBLIC_APP_URL.startswith("https://")


def attachment_file(request, token):
    try:
        data = signing.loads(token, salt=SALT, max_age=URL_MAX_AGE)
    except signing.BadSignature:
        return HttpResponse(status=403)
    attachment = get_object_or_404(
        MessageAttachment.objects.for_workspace(data["workspace"]), pk=data["attachment"]
    )
    response = HttpResponse(base64.b64decode(attachment.data), content_type=attachment.content_type)
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response
