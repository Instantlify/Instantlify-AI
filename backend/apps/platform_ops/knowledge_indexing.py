"""Shared status for the manually requested support knowledge indexing job."""

import uuid

from django.core.cache import cache

STATUS_KEY = "ops:knowledge_indexing:status"
LOCK_KEY = "ops:knowledge_indexing:lock"


def set_status(state, message):
    cache.set(STATUS_KEY, {"state": state, "message": message}, 86400)


def status():
    result = cache.get(STATUS_KEY) or {"state": "idle", "message": ""}
    if result["state"] in {"queued", "running"} and not cache.get(LOCK_KEY):
        return {
            "state": "failed",
            "message": "Indexing did not finish. Check the worker and retry Re-embed all.",
        }
    return result


def enqueue():
    from .tasks import embed_platform_knowledge

    token = uuid.uuid4().hex
    if not cache.add(LOCK_KEY, token, 600):
        return
    set_status("queued", "Re-embedding queued. Waiting for the background worker.")
    try:
        embed_platform_knowledge.delay(token)
    except Exception:
        set_status(
            "failed",
            "Could not start re-embedding. Check that Redis and the background worker are available, then retry.",
        )
        cache.delete(LOCK_KEY)
