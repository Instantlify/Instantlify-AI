"""Link-in-bio blocks and themes.

A page is an ordered list of up to 40 blocks. Every URL is validated here, video
links are turned into embed URLs for an allow-listed set of hosts on the server (the
browser never embeds an arbitrary page), and email-signup blocks create CRM contacts
through the public endpoint. Pages saved before blocks existed keep their `links`.
"""

import re
from urllib.parse import parse_qs, urlsplit

from rest_framework import serializers

THEMES = {"light", "dark", "gradient", "minimal", "bold"}
MAX_BLOCKS = 40
SOCIAL_PLATFORMS = {
    "instagram",
    "tiktok",
    "youtube",
    "x",
    "facebook",
    "linkedin",
    "whatsapp",
    "telegram",
    "email",
    "website",
}
TYPES = {"link", "heading", "text", "image", "video", "social", "email_capture", "divider"}


def _https(url, field="URL"):
    url = str(url or "").strip()
    if not url.startswith("https://") or len(url) > 2000 or any(c.isspace() for c in url):
        raise serializers.ValidationError(f"{field} must be a full https:// address.")
    return url


def _text(value, limit, field, required=True):
    text = str(value or "").strip()
    if required and not text:
        raise serializers.ValidationError(f"{field} is required.")
    if len(text) > limit:
        raise serializers.ValidationError(f"{field} can have at most {limit} characters.")
    return text


def embed_url(url):
    """The privacy-friendly embed address for YouTube, Vimeo or Loom, else None."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    video_id = ""
    if host == "youtube.com":
        video_id = (parse_qs(parts.query).get("v") or [""])[0]
        if not video_id and parts.path.startswith(("/shorts/", "/embed/")):
            video_id = parts.path.split("/")[2]
        if re.fullmatch(r"[\w-]{6,20}", video_id or ""):
            return f"https://www.youtube-nocookie.com/embed/{video_id}"
    if host == "youtu.be":
        video_id = parts.path.strip("/")
        if re.fullmatch(r"[\w-]{6,20}", video_id):
            return f"https://www.youtube-nocookie.com/embed/{video_id}"
    if host == "vimeo.com":
        video_id = parts.path.strip("/").split("/")[0]
        if video_id.isdigit():
            return f"https://player.vimeo.com/video/{video_id}"
    if host == "loom.com" and parts.path.startswith("/share/"):
        video_id = parts.path.split("/")[2]
        if re.fullmatch(r"[0-9a-f]{16,64}", video_id):
            return f"https://www.loom.com/embed/{video_id}"
    return None


def validate_blocks(value):
    if not isinstance(value, list) or len(value) > MAX_BLOCKS:
        raise serializers.ValidationError(f"Add up to {MAX_BLOCKS} blocks.")
    cleaned = []
    for block in value:
        if not isinstance(block, dict) or block.get("type") not in TYPES:
            raise serializers.ValidationError("Unknown block type.")
        kind = block["type"]
        item = {"type": kind}
        if kind == "link":
            item["title"] = _text(block.get("title"), 60, "Link title")
            url = str(block.get("url") or "").strip()
            item["url"] = url if url.startswith("mailto:") and len(url) <= 300 else _https(url)
            if block.get("highlight") is True:
                item["highlight"] = True
        elif kind == "heading":
            item["text"] = _text(block.get("text"), 80, "Heading")
        elif kind == "text":
            item["text"] = _text(block.get("text"), 1000, "Text")
        elif kind == "image":
            item["url"] = _https(block.get("url"), "Image")
            item["alt"] = _text(block.get("alt"), 150, "Image description", required=False)
            if block.get("link"):
                item["link"] = _https(block.get("link"), "Image link")
        elif kind == "video":
            item["url"] = _https(block.get("url"), "Video")
            embed = embed_url(item["url"])
            if not embed:
                raise serializers.ValidationError("Use a YouTube, Vimeo or Loom video link.")
            item["embed"] = embed
        elif kind == "social":
            items = block.get("items")
            if not isinstance(items, list) or not 1 <= len(items) <= 10:
                raise serializers.ValidationError("A social row needs 1–10 profiles.")
            item["items"] = []
            for entry in items:
                platform = str((entry or {}).get("platform", ""))
                if platform not in SOCIAL_PLATFORMS:
                    raise serializers.ValidationError("Choose a supported social network.")
                url = str(entry.get("url") or "").strip()
                if platform == "email":
                    if not re.fullmatch(r"mailto:[^\s@]+@[^\s@]+\.[^\s@]+", url):
                        raise serializers.ValidationError(
                            "Email profiles use mailto:you@example.com."
                        )
                else:
                    url = _https(url, f"{platform} link")
                item["items"].append({"platform": platform, "url": url})
        elif kind == "email_capture":
            item["title"] = _text(block.get("title") or "Join the list", 80, "Signup title")
            item["button"] = _text(block.get("button") or "Subscribe", 30, "Button text")
            item["tag"] = _text(block.get("tag") or "bio-signup", 40, "Tag")
        cleaned.append(item)
    return cleaned


def public_block(index, block):
    """What the anonymous page receives. Link targets go through the click endpoint."""
    data = {"index": index, **block}
    if block["type"] == "email_capture":
        data.pop("tag", None)
    return data
