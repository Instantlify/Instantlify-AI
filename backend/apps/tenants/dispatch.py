from django.core.cache import cache


def enqueue_once(task, workspace_id, pk, ttl=30):
    """Beat polls durable rows every few seconds. Skip IDs that are already queued so a
    backlog is not multiplied; the marker expires, so a lost broker message is resent."""
    if cache.add(f"enqueued:{task.name}:{pk}", 1, ttl):
        task.delay(str(workspace_id), str(pk))
