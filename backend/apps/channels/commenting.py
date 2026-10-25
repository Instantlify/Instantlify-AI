"""Public comment replies share the durable outbound delivery queue."""

import hashlib
import json
import re

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from apps.tenants.services import audit

POST_ID = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")


def validate_comment_settings(graph):
    posts = graph.get("comment_post_ids", [])
    replies = graph.get("comment_replies", [])
    mode = graph.get("comment_post_mode", "specific" if posts else "all")
    if not isinstance(mode, str) or mode not in {"all", "specific", "next"}:
        raise ValidationError("Choose all posts, specific posts or the next post.")
    if (
        not isinstance(posts, list)
        or len(posts) > 50
        or any(not isinstance(post, str) or not POST_ID.fullmatch(post) for post in posts)
    ):
        raise ValidationError("Choose up to 50 valid post IDs.")
    if (
        not isinstance(replies, list)
        or len(replies) > 10
        or any(
            not isinstance(reply, str) or not 1 <= len(reply.strip()) <= 1000 for reply in replies
        )
    ):
        raise ValidationError("Use up to 10 public replies, each with 1–1000 characters.")
    if mode == "specific" and not posts:
        raise ValidationError("Choose at least one post.")
    if mode != "specific" and posts:
        raise ValidationError("Only specific-post targeting accepts a post list.")
    if posts or replies or mode == "next":
        if not graph.get("connection_id") or any(
            trigger["kind"] != "comment" or trigger.get("channel") not in {"instagram", "messenger"}
            for trigger in graph["triggers"]
        ):
            raise ValidationError(
                "Post targeting and public replies require a connected Instagram or Facebook comment trigger."
            )


def first_post_after(fetch_page, since, timestamp_field):
    """Use account-owned pages and opaque cursors; never follow a returned URL."""
    from .transport import ProviderError

    candidates, after = [], None
    for _ in range(10):
        body = fetch_page(after)
        rows = body.get("data", [])
        all_older = bool(rows)
        for post in rows:
            when = parse_datetime(str(post.get(timestamp_field) or ""))
            post_id = str(post.get("id") or "")
            if not when or timezone.is_naive(when) or not POST_ID.fullmatch(post_id):
                raise ProviderError("post_timestamp_unavailable")
            if when > since:
                all_older = False
                candidates.append((when, post_id))
        paging = body.get("paging") or {}
        if all_older or not paging.get("next"):
            return min(candidates)[1] if candidates else None
        after = (paging.get("cursors") or {}).get("after")
        if not rows or not isinstance(after, str) or not 1 <= len(after) <= 2000:
            raise ProviderError("post_pagination_unavailable")
    raise ProviderError("post_history_limit")


def matches_comment_target(automation, message, payload):
    graph = automation.published
    mode = graph.get("comment_post_mode", "specific" if graph.get("comment_post_ids") else "all")
    if mode == "all":
        return True
    post_id = payload.get("post_id")
    if not post_id or payload.get("kind") != "comment":
        return False
    if mode == "specific":
        return post_id in graph.get("comment_post_ids", [])
    from apps.automations.models import Automation

    from .adapters import adapter_for

    # All conversations use one resolved post, even when their comments arrive together.
    locked = (
        Automation.objects.for_workspace(automation.workspace_id)
        .select_for_update()
        .get(pk=automation.pk)
    )
    if not locked.enabled:
        return False
    graph = dict(locked.published)
    target = graph.get("resolved_next_post_id")
    if not target:
        since = parse_datetime(str(graph.get("comment_since") or ""))
        if not since or timezone.is_naive(since):
            return False
        target = adapter_for(message.conversation.identity.connection).next_post(since)
        if not target:
            return False
        graph["resolved_next_post_id"] = target
        locked.published = graph
        locked.save(update_fields=["published"])
        audit(message.conversation.workspace, None, "automation.next_post_resolved", automation.pk)
    automation.published = graph
    return post_id == target


def queue_public_reply(message, payload, automation):
    from apps.crm.models import Message
    from apps.platform_ops.security import assert_enabled

    from .models import Delivery

    replies = automation.published.get("comment_replies", [])
    comment_id = payload.get("comment_id", "")
    if not replies or not isinstance(comment_id, str) or not POST_ID.fullmatch(comment_id):
        return
    assert_enabled(message.workspace_id, "messaging")
    # The selection is stable on webhook retries, independently of worker scheduling.
    index = int(hashlib.sha256(comment_id.encode()).hexdigest(), 16) % len(replies)
    text = replies[index].strip()
    delivery, created = Delivery.objects.for_workspace(message.workspace_id).get_or_create(
        idempotency_key=f"flow:comment:{automation.pk}:{message.event_id}",
        defaults={
            "workspace_id": message.workspace_id,
            "connection": message.conversation.identity.connection,
            "recipient_id": comment_id,
            "payload": json.dumps(
                {"kind": "public_comment", "text": text, "automation_id": str(automation.pk)}
            ),
            "available_at": timezone.now(),
        },
    )
    if created:
        Message.objects.for_workspace(message.workspace_id).create(
            workspace_id=message.workspace_id,
            conversation=message.conversation,
            direction="outbound",
            kind="public_reply",
            text=text,
            delivery=delivery,
        )
        audit(message.conversation.workspace, None, "comment.reply_queued", delivery.pk)
    return delivery
