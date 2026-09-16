from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.channels.adapters import IntegrationUnavailable, adapter_for
from apps.channels.tasks import rate_limit_wait
from apps.channels.transport import AmbiguousDelivery, ProviderError, RetryableError
from apps.platform_ops.security import pause_guard
from apps.tenants.dispatch import enqueue_once
from apps.tenants.services import audit

from .models import ScheduledPost

MAX_ATTEMPTS = 5


@shared_task(ignore_result=True)
def dispatch_scheduled_posts():
    for wid, pk in ScheduledPost.all_objects.filter(
        status="scheduled", scheduled_at__lte=timezone.now()
    ).values_list("workspace_id", "pk")[:50]:
        enqueue_once(publish_post, wid, pk, ttl=120)
    # A worker lost mid-publish may or may not have published; never re-post blindly.
    ScheduledPost.all_objects.filter(
        status="publishing", updated_at__lt=timezone.now() - timedelta(minutes=10)
    ).update(status="unknown", error_code="worker_interrupted")


@shared_task(ignore_result=True, soft_time_limit=100, time_limit=120)
@pause_guard("content", "integration:instagram")
def publish_post(workspace_id, post_id):
    with transaction.atomic():
        post = (
            ScheduledPost.objects.for_workspace(workspace_id)
            .select_for_update()
            .select_related("connection")
            .filter(pk=post_id, status="scheduled", scheduled_at__lte=timezone.now())
            .first()
        )
        if not post:
            return
        connection = post.connection
        if connection.status != "active" or connection.expires_at <= timezone.now():
            post.status = "failed"
            post.error_code = "connection_unavailable"
            post.save()
            return
        wait = rate_limit_wait(connection)
        if wait:
            post.scheduled_at = timezone.now() + timedelta(seconds=wait)
            post.save(update_fields=["scheduled_at"])
            return
        post.status = "publishing"
        post.attempts += 1
        post.save()
    try:
        provider_id = adapter_for(connection).publish_post(
            caption=post.caption, media_url=post.media_url, media_type=post.media_type
        )
        if not provider_id:
            raise AmbiguousDelivery()
    except RetryableError as exc:
        post.status = "scheduled" if post.attempts < MAX_ATTEMPTS else "failed"
        post.error_code = exc.code
        post.scheduled_at = timezone.now() + timedelta(seconds=max(exc.delay, 60 * post.attempts))
    except AmbiguousDelivery:
        post.status = "unknown"
        post.error_code = "publish_unknown"
    except (ProviderError, IntegrationUnavailable, NotImplementedError) as exc:
        post.status = "failed"
        post.error_code = getattr(exc, "code", "unsupported_provider")
    else:
        post.status = "published"
        post.provider_post_id = str(provider_id)
        post.published_at = timezone.now()
    post.save()
    audit(connection.workspace, None, "post." + post.status, post.id)
