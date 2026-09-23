"""Uptime probe: failures page once after two misses, recovery resolves, pager errors
never break the probe."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.platform_ops import uptime

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def channels(settings):
    cache.clear()
    settings.UPTIME_PROBE_URL = "https://app.example.com/health/ready/"
    settings.UPTIME_LATENCY_MS = 2500
    settings.ALERT_WEBHOOK_URL = "https://hooks.example.com/alert"
    settings.PAGERDUTY_ROUTING_KEY = "pd-key"


def response(status=200):
    return MagicMock(status_code=status)


def sent(post):
    return [(call.args[0], call.kwargs["json"]) for call in post.call_args_list]


def test_ingress_outage_pages_once_then_resolves():
    with (
        patch("apps.platform_ops.uptime.httpx.get", return_value=response(503)),
        patch("apps.platform_ops.uptime.httpx.post") as post,
    ):
        assert uptime.probe_uptime()["ingress"].startswith("HTTP 503 in")
        assert post.call_count == 0  # one miss is a blip, not an incident
        uptime.probe_uptime()
        uptime.probe_uptime()  # still down: no repeat page
    messages = sent(post)
    assert len(messages) == 2  # Slack text + PagerDuty trigger, once
    slack = next(body for url, body in messages if url == "https://hooks.example.com/alert")
    assert slack["text"].startswith("[Nemio] DOWN ingress: HTTP 503")
    pager = next(body for url, body in messages if "pagerduty" in url)
    assert (pager["event_action"], pager["dedup_key"]) == ("trigger", "nemio:ingress")
    with (
        patch("apps.platform_ops.uptime.httpx.get", return_value=response(200)),
        patch("apps.platform_ops.uptime.httpx.post") as post,
    ):
        uptime.probe_uptime()
        uptime.probe_uptime()
    resolved = sent(post)
    assert len(resolved) == 2  # resolved once, then quiet
    assert any(body.get("event_action") == "resolve" for _, body in resolved)


def test_slow_and_unreachable_ingress_are_failures(settings):
    with patch("apps.platform_ops.uptime.time.monotonic", side_effect=[0, 3.2]):
        with patch("apps.platform_ops.uptime.httpx.get", return_value=response()):
            assert uptime.check_ingress() == "slow: 3200 ms (limit 2500 ms)"
    with patch("apps.platform_ops.uptime.httpx.get", side_effect=httpx.ConnectError("x")):
        assert uptime.check_ingress() == "unreachable (ConnectError)"
    settings.UPTIME_PROBE_URL = ""
    assert uptime.check_ingress() is None  # unconfigured is silence, not "ok"


def test_dead_letters_and_backlogs_are_reported(workspace):
    from apps.channels.models import ChannelConnection, WebhookEvent

    channel = ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id="a",
        display_name="x",
        access_token="t",
        expires_at=timezone.now() + timedelta(days=1),
        is_test=True,
    )
    old = timezone.now() - timedelta(minutes=10)
    for event_id, status in [("dead", "failed"), ("stuck", "pending")]:
        event = WebhookEvent.objects.for_workspace(workspace).create(
            workspace=workspace,
            connection=channel,
            event_id=event_id,
            payload="{}",
            available_at=old,
            status=status,
        )
        WebhookEvent.all_objects.filter(pk=event.pk).update(created_at=old)
    assert uptime.check_dead_letters().startswith("1 inbound webhook(s) failed")
    assert uptime.check_backlogs() == "pending over 5 min: 1 inbound webhooks"


def test_a_broken_pager_or_crashing_check_never_stops_the_probe():
    def boom():
        raise RuntimeError("bug")

    with (
        patch.dict(uptime.CHECKS, {"dependencies": boom}),
        patch("apps.platform_ops.uptime.httpx.get", return_value=response(200)),
        patch("apps.platform_ops.uptime.httpx.post", side_effect=httpx.ConnectError("down")),
    ):
        uptime.probe_uptime()
        results = uptime.probe_uptime()  # second miss pages; the pager is down too
    assert results["dependencies"] == "check crashed (RuntimeError)"
    assert cache.get(uptime.STATE_KEY)["dependencies"]["paged"] is True
