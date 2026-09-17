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
# Meta media containers expire 24 hours after creation.
CONTAINER_LIFETIME = timedelta(hours=24)


def poll_delay(polls):
    """Seconds until the next status check: 30s, 60s, 120s … capped at ten minutes.
    Video processing is usually done within a few minutes; polling every second
    would burn the account's hourly API budget."""
    return min(600, 30 * 2**polls)


@shared_task(ignore_result=True)
def dispatch_scheduled_posts():
    now = timezone.now()
    # Lost before a container was recorded: nothing was created or published, so a
    # plain retry is safe. Containers are idempotent to abandon; publishes are not.
    ScheduledPost.all_objects.filter(
        status="publishing", container_id="", updated_at__lt=now - timedelta(minutes=10)
    ).update(status="scheduled", error_code="worker_interrupted", scheduled_at=now)
    ScheduledPost.all_objects.filter(
        status="publishing", container_created_at__lt=now - CONTAINER_LIFETIME
    ).exclude(container_id="").update(status="failed", error_code="container_expired")
    for wid, pk in ScheduledPost.all_objects.filter(
        status__in=["scheduled", "publishing"], scheduled_at__lte=now
    ).values_list("workspace_id", "pk")[:50]:
        enqueue_once(publish_post, wid, pk, ttl=120)


@shared_task(ignore_result=True, soft_time_limit=100, time_limit=120)
@pause_guard("content", "integration:instagram")
def publish_post(workspace_id, post_id):
    with transaction.atomic():
        post = (
            ScheduledPost.objects.for_workspace(workspace_id)
            .select_for_update()
            .select_related("connection")
            .filter(
                pk=post_id, status__in=["scheduled", "publishing"], scheduled_at__lte=timezone.now()
            )
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
        creating = post.status == "scheduled"
        if creating:
            post.status = "publishing"
            post.attempts += 1
            post.save()
    adapter = adapter_for(connection)
    try:
        if creating:
            container_id = adapter.create_media_container(
                caption=post.caption, media_url=post.media_url, media_type=post.media_type
            )
            post.container_id = container_id
            post.container_created_at = timezone.now()
            post.polls = 0
            # Persist before anything that could publish, so a crash resumes here.
            post.save(update_fields=["container_id", "container_created_at", "polls", "updated_at"])
        state = adapter.container_status(post.container_id)
        if state == "IN_PROGRESS":
            post.scheduled_at = timezone.now() + timedelta(seconds=poll_delay(post.polls))
            post.polls += 1
            post.error_code = ""
            post.save(update_fields=["scheduled_at", "polls", "error_code", "updated_at"])
            return
        if state == "PUBLISHED":
            # A previous attempt published but never recorded it (crash or ambiguous
            # response). The container is spent, so do not publish again.
            provider_id = ""
        elif state == "FINISHED":
            provider_id = adapter.publish_container(post.container_id)
            if not provider_id:
                raise AmbiguousDelivery()
        else:
            raise ProviderError(
                "container_expired" if state == "EXPIRED" else "media_processing_failed"
            )
    except RetryableError as exc:
        if creating:
            post.status = "scheduled" if post.attempts < MAX_ATTEMPTS else "failed"
            post.error_code = exc.code
            post.scheduled_at = timezone.now() + timedelta(
                seconds=max(exc.delay, 60 * post.attempts)
            )
        else:
            # A throttled status check or publish is retried; the container is still ours.
            post.error_code = exc.code
            post.scheduled_at = timezone.now() + timedelta(seconds=exc.delay)
    except AmbiguousDelivery:
        # The publish call may have gone through. The next poll asks the container,
        # which reports PUBLISHED if it did, instead of guessing.
        post.error_code = "publish_unknown"
        post.scheduled_at = timezone.now() + timedelta(seconds=poll_delay(post.polls))
        post.polls += 1
    except (ProviderError, IntegrationUnavailable, NotImplementedError) as exc:
        post.status = "failed"
        post.error_code = getattr(exc, "code", "unsupported_provider")
    else:
        post.status = "published"
        post.provider_post_id = str(provider_id)
        post.error_code = ""
        post.published_at = timezone.now()
    post.save()
    audit(connection.workspace, None, "post." + post.status, post.id)
