from celery import shared_task
from django.core.cache import cache
from django.utils import timezone


@shared_task
def health_check():
    checked_at = timezone.now().isoformat()
    cache.set("worker:last_heartbeat", checked_at, timeout=90)
    return {"status": "ok", "checked_at": checked_at}


@shared_task(ignore_result=True)
def check_backlogs():
    import logging
    from datetime import timedelta

    from apps.agents.models import AgentRun
    from apps.channels.models import Delivery, WebhookEvent

    cutoff = timezone.now() - timedelta(minutes=5)
    counts = {
        model._meta.model_name: model.all_objects.filter(
            status="pending", created_at__lt=cutoff
        ).count()
        for model in [WebhookEvent, Delivery, AgentRun]
    }
    # An inbound event that exhausted its retries is a lost customer message.
    counts["webhookevent_failed"] = WebhookEvent.all_objects.filter(
        status="failed", created_at__gte=timezone.now() - timedelta(hours=1)
    ).count()
    cache.set("operations:backlogs", counts, timeout=180)
    if any(counts.values()):
        logging.getLogger(__name__).warning(
            "Queue backlog requires operator attention", extra={"event_code": "queue_backlog"}
        )
