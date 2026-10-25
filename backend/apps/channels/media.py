"""Validation shared by graph publication, queuing and provider delivery."""

import ipaddress
from urllib.parse import urlsplit

from rest_framework.exceptions import ValidationError

MEDIA_CHANNELS = {"instagram", "messenger", "whatsapp", "telegram"}
MEDIA_TYPES = {"image", "video", "audio"}


def validate_media(media_url, media_type):
    if (
        not isinstance(media_type, str)
        or media_type not in MEDIA_TYPES
        or not isinstance(media_url, str)
    ):
        raise ValidationError("Choose an image, video or audio file URL.")
    try:
        url = urlsplit(media_url)
        host = (url.hostname or "").lower().rstrip(".")
        valid = (
            url.scheme == "https"
            and host
            and not url.username
            and not url.password
            and not url.fragment
            and url.port in {None, 443}
            and len(media_url) <= 2000
            and not any(c.isspace() for c in media_url)
            and host != "localhost"
            and not host.endswith((".localhost", ".local", ".internal"))
        )
        try:
            valid = valid and ipaddress.ip_address(host).is_global
        except ValueError:
            valid = valid and "." in host
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise ValidationError("Use a public HTTPS media URL without credentials or fragments.")


def validate_media_channels(graph):
    if not any(n["data"]["kind"] == "send_media" for n in graph["nodes"]):
        return
    if any(t.get("channel") not in MEDIA_CHANNELS for t in graph["triggers"]):
        raise ValidationError(
            "Media steps need an explicit Instagram, Messenger, WhatsApp or Telegram channel."
        )
