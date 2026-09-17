"""Instagram publishing: container persisted, processing polled, publish only when ready."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.channels.models import ChannelConnection
from apps.channels.transport import AmbiguousDelivery, RetryableError
from apps.content.models import ScheduledPost
from apps.content.tasks import dispatch_scheduled_posts, publish_post

pytestmark = pytest.mark.django_db


@pytest.fixture
def channel(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id="ig-account",
        display_name="Test",
        access_token="secret",
        expires_at=timezone.now() + timedelta(days=60),
        is_test=True,
    )


def video(workspace, channel, **fields):
    return ScheduledPost.objects.for_workspace(workspace).create(
        workspace=workspace,
        connection=channel,
        caption="Reel",
        media_url="https://cdn.example.com/x.mp4",
        media_type="video",
        scheduled_at=timezone.now(),
        **fields,
    )


def run(post, adapter):
    ScheduledPost.all_objects.filter(pk=post.pk).update(scheduled_at=timezone.now())
    with patch("apps.content.tasks.adapter_for", return_value=adapter):
        publish_post(str(post.workspace_id), str(post.id))
    post.refresh_from_db()
    return post


class Adapter:
    def __init__(self, statuses, publish="media-1"):
        self.statuses = list(statuses)
        self.publish = publish
        self.created = 0
        self.published = 0

    def create_media_container(self, **kwargs):
        self.created += 1
        return "container-1"

    def container_status(self, container_id):
        assert container_id == "container-1"
        return self.statuses.pop(0)

    def publish_container(self, container_id):
        self.published += 1
        if isinstance(self.publish, Exception):
            raise self.publish
        return self.publish


def test_video_waits_for_processing_then_publishes(workspace, channel):
    post = video(workspace, channel)
    adapter = Adapter(["IN_PROGRESS", "IN_PROGRESS", "FINISHED"])
    run(post, adapter)
    assert (post.status, post.container_id, post.polls) == ("publishing", "container-1", 1)
    assert post.container_created_at is not None and adapter.published == 0
    assert post.scheduled_at > timezone.now() + timedelta(seconds=20)
    with patch.object(publish_post, "delay") as delay:
        dispatch_scheduled_posts()
        delay.assert_not_called()  # not due for the next poll yet
    run(post, adapter)
    assert (post.status, post.polls) == ("publishing", 2)
    assert post.scheduled_at > timezone.now() + timedelta(seconds=50)  # backoff grew
    run(post, adapter)
    assert (post.status, post.provider_post_id, post.error_code) == ("published", "media-1", "")
    assert (adapter.created, adapter.published, post.attempts) == (1, 1, 1)
    # Nothing left to do: a re-run is a no-op.
    run(post, adapter)
    assert adapter.published == 1


def test_processing_failure_never_publishes(workspace, channel):
    post = video(workspace, channel)
    adapter = Adapter(["ERROR"])
    run(post, adapter)
    assert (post.status, post.error_code) == ("failed", "media_processing_failed")
    assert adapter.published == 0
    expired = video(workspace, channel)
    run(expired, Adapter(["EXPIRED"]))
    assert (expired.status, expired.error_code) == ("failed", "container_expired")


def test_ambiguous_publish_is_resolved_by_the_container(workspace, channel):
    post = video(workspace, channel)
    adapter = Adapter(["FINISHED", "PUBLISHED"], publish=AmbiguousDelivery())
    run(post, adapter)
    assert (post.status, post.error_code) == ("publishing", "publish_unknown")
    adapter.publish = "would-double-post"
    run(post, adapter)
    assert (post.status, post.error_code, post.provider_post_id) == ("published", "", "")
    assert adapter.published == 1  # never published twice


def test_throttled_poll_keeps_the_container(workspace, channel):
    post = video(workspace, channel)
    adapter = Adapter(["IN_PROGRESS", "FINISHED"])
    run(post, adapter)
    throttled = Adapter([], publish="x")
    throttled.container_status = lambda container_id: (_ for _ in ()).throw(RetryableError(90))
    run(post, throttled)
    assert (post.status, post.container_id, post.error_code) == (
        "publishing",
        "container-1",
        "rate_limited",
    )
    assert post.scheduled_at > timezone.now() + timedelta(seconds=80)
    run(post, adapter)
    assert (post.status, adapter.created) == ("published", 1)


def test_dispatcher_recovers_lost_workers_safely(workspace, channel):
    stale = timezone.now() - timedelta(minutes=11)
    no_container = video(workspace, channel, status="publishing")
    expired = video(
        workspace,
        channel,
        status="publishing",
        container_id="old",
        container_created_at=timezone.now() - timedelta(hours=25),
    )
    polling = video(
        workspace,
        channel,
        status="publishing",
        container_id="c",
        container_created_at=timezone.now(),
    )
    ScheduledPost.all_objects.filter(pk__in=[no_container.pk, expired.pk]).update(updated_at=stale)
    with patch.object(publish_post, "delay") as delay:
        dispatch_scheduled_posts()
        queued = {call.args[1] for call in delay.call_args_list}
    for post in [no_container, expired, polling]:
        post.refresh_from_db()
    assert (no_container.status, no_container.error_code) == ("scheduled", "worker_interrupted")
    assert (expired.status, expired.error_code) == ("failed", "container_expired")
    assert polling.status == "publishing"
    assert queued == {str(no_container.pk), str(polling.pk)}
