"""Uptime probing and paging.

Every minute the worker checks the things a customer would notice first: the public
ingress answering quickly, the database and Redis, inbound webhooks that exhausted their
retries (lost customer messages), and queues that stopped draining. A check that fails
twice in a row pages; the first success after that resolves the page. One page per
incident, not one per minute.

Channels, each optional: ALERT_WEBHOOK_URL (Slack-compatible incoming webhook: a JSON
`text` field) and PAGERDUTY_ROUTING_KEY (Events API v2, trigger/resolve by dedup key).

A probe cannot report its own death: if the Celery worker stops, this task stops too.
`/health/ready/` returns 503 when the worker heartbeat is missing, so point an external
monitor (UptimeRobot, Better Stack, PagerDuty synthetics) at it as the outer loop.
"""

import logging
import time
from datetime import timedelta

import httpx
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

FAILURES_BEFORE_PAGE = 2
STATE_KEY = "uptime:state"
LAST_KEY = "uptime:last"
log = logging.getLogger(__name__)


def check_ingress():
    """The public URL, end to end through DNS, TLS, the proxy and Django."""
    url = settings.UPTIME_PROBE_URL
    if not url:
        return None  # not configured: nothing to say, rather than a false "ok"
    started = time.monotonic()
    try:
        response = httpx.get(url, timeout=10, follow_redirects=False)
    except httpx.HTTPError as exc:
        return f"unreachable ({type(exc).__name__})"
    ms = int((time.monotonic() - started) * 1000)
    if response.status_code >= 500:
        return f"HTTP {response.status_code} in {ms} ms"
    if ms > settings.UPTIME_LATENCY_MS:
        return f"slow: {ms} ms (limit {settings.UPTIME_LATENCY_MS} ms)"
    return ""


def check_dependencies():
    from apps.dashboard_api.views import dependency_status

    checks = dependency_status()
    checks.pop("worker", None)  # this task running is the worker's proof of life
    down = [name for name, ok in checks.items() if not ok]
    return f"{', '.join(down)} unavailable" if down else ""


def check_dead_letters():
    from apps.channels.models import WebhookEvent

    failed = WebhookEvent.all_objects.filter(
        status="failed", created_at__gte=timezone.now() - timedelta(hours=1)
    ).count()
    return f"{failed} inbound webhook(s) failed permanently in the last hour" if failed else ""


def check_backlogs():
    from apps.agents.models import AgentRun
    from apps.channels.models import Delivery, WebhookEvent

    cutoff = timezone.now() - timedelta(minutes=5)
    stuck = {
        label: model.all_objects.filter(status="pending", created_at__lt=cutoff).count()
        for label, model in [
            ("inbound webhooks", WebhookEvent),
            ("deliveries", Delivery),
            ("agent runs", AgentRun),
        ]
    }
    stuck = {label: count for label, count in stuck.items() if count}
    return (
        "pending over 5 min: " + ", ".join(f"{count} {label}" for label, count in stuck.items())
        if stuck
        else ""
    )


CHECKS = {
    "ingress": check_ingress,
    "dependencies": check_dependencies,
    "dead_letters": check_dead_letters,
    "backlogs": check_backlogs,
}


def notify(check, problem, *, resolved=False):
    """Deliver to every configured channel. Delivery failures are logged, never raised:
    a broken pager must not stop the next probe."""
    title = f"[Nemio] {'RESOLVED' if resolved else 'DOWN'} {check}"
    summary = f"{title}: {problem}" if problem else title
    if settings.ALERT_WEBHOOK_URL:
        try:
            httpx.post(settings.ALERT_WEBHOOK_URL, json={"text": summary}, timeout=10)
        except httpx.HTTPError:
            log.warning("Alert webhook failed", extra={"event_code": "uptime_alert_failed"})
    if settings.PAGERDUTY_ROUTING_KEY:
        event = {
            "routing_key": settings.PAGERDUTY_ROUTING_KEY,
            "event_action": "resolve" if resolved else "trigger",
            "dedup_key": f"nemio:{check}",
        }
        if not resolved:
            event["payload"] = {
                "summary": summary[:1024],
                "source": settings.PUBLIC_APP_URL or "nemio",
                "severity": "critical",
                "component": check,
            }
        try:
            httpx.post("https://events.pagerduty.com/v2/enqueue", json=event, timeout=10)
        except httpx.HTTPError:
            log.warning("PagerDuty event failed", extra={"event_code": "uptime_pager_failed"})


@shared_task(ignore_result=True, soft_time_limit=45, time_limit=60)
def probe_uptime():
    state = cache.get(STATE_KEY) or {}
    results = {}
    for name, check in CHECKS.items():
        try:
            problem = check()
        except Exception as exc:  # a check that crashes is itself a failure to report
            problem = f"check crashed ({type(exc).__name__})"
        results[name] = problem
        if problem is None:
            continue
        current = state.get(name, {"failures": 0, "paged": False})
        if problem:
            current["failures"] += 1
            if current["failures"] >= FAILURES_BEFORE_PAGE and not current["paged"]:
                notify(name, problem)
                current["paged"] = True
        else:
            if current["paged"]:
                notify(name, "", resolved=True)
            current = {"failures": 0, "paged": False}
        state[name] = current
    cache.set(STATE_KEY, state, timeout=None)
    cache.set(LAST_KEY, {"at": timezone.now().isoformat(), "results": results}, timeout=600)
    return results
