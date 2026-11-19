import hashlib
import hmac
import ipaddress
import socket
import time
from datetime import timedelta
from urllib.parse import urlparse

import httpx
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.tenants.dispatch import enqueue_once

from .models import OutboundWebhook, WebhookSubscription

MAX_ATTEMPTS = 8
DISABLE_AFTER_FAILURES = 50


def sign(secret, timestamp, body):
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


def is_public_https(url):
    """Refuse private/loopback targets so subscriptions cannot probe the internal network."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            return False
    return True


@shared_task(ignore_result=True)
def dispatch_outbound_webhooks():
    for wid, pk in OutboundWebhook.all_objects.filter(
        status="pending", available_at__lte=timezone.now()
    ).values_list("workspace_id", "pk")[:100]:
        enqueue_once(deliver_webhook, wid, pk)


@shared_task(ignore_result=True, soft_time_limit=40, time_limit=50)
def deliver_webhook(workspace_id, hook_id):
    from apps.platform_ops.security import blocked

    if blocked(workspace_id):
        return
    with transaction.atomic():
        hook = (
            OutboundWebhook.objects.for_workspace(workspace_id)
            .select_for_update()
            .select_related("subscription")
            .filter(pk=hook_id, status="pending", available_at__lte=timezone.now())
            .first()
        )
        if not hook:
            return
        subscription = hook.subscription
        if not subscription.active:
            hook.status = "cancelled"
            hook.save(update_fields=["status"])
            return
        hook.status = "sending"
        hook.attempts += 1
        hook.save(update_fields=["status", "attempts"])
    body = hook.payload.encode()
    timestamp = int(time.time())
    code = None
    try:
        if not is_public_https(subscription.url):
            raise ValueError("private_target")
        response = httpx.post(
            subscription.url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Instantlify-Webhooks/1.0",
                "X-Instantlify-Event": hook.event,
                "X-Instantlify-Delivery": str(hook.id),
                "X-Instantlify-Signature": sign(subscription.secret, timestamp, body),
                **({"X-Instantlify-Token": subscription.token} if subscription.token else {}),
            },
            timeout=httpx.Timeout(10, connect=5),
            follow_redirects=False,
        )
        code = response.status_code
        ok = 200 <= code < 300
    except (httpx.HTTPError, ValueError):
        ok = False
    with transaction.atomic():
        hook = (
            OutboundWebhook.objects.for_workspace(workspace_id).select_for_update().get(pk=hook.pk)
        )
        hook.response_code = code
        if ok:
            hook.status = "delivered"
            hook.delivered_at = timezone.now()
            WebhookSubscription.objects.for_workspace(workspace_id).filter(
                pk=subscription.pk
            ).update(failure_count=0, last_delivered_at=timezone.now())
        else:
            hook.status = "pending" if hook.attempts < MAX_ATTEMPTS else "failed"
            hook.available_at = timezone.now() + timedelta(seconds=min(3600, 15 * 3**hook.attempts))
            failures = subscription.failure_count + 1
            # A dead endpoint is disabled rather than retried forever.
            WebhookSubscription.objects.for_workspace(workspace_id).filter(
                pk=subscription.pk
            ).update(failure_count=failures, active=failures < DISABLE_AFTER_FAILURES)
        hook.save()
