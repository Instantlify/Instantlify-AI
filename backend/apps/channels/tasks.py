import json
import random
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from redis import Redis
from rest_framework.exceptions import ValidationError

from apps.platform_ops.security import blocked, pause_guard
from apps.tenants.dispatch import enqueue_once
from apps.tenants.services import audit

from .adapters import Credentials, IntegrationUnavailable, adapter_for
from .models import ChannelConnection, Delivery, WebhookEvent
from .transport import AmbiguousDelivery, ProviderError, RetryableError

MAX_WEBHOOK_ATTEMPTS = 6
META_PROVIDERS = {"instagram", "whatsapp", "messenger"}

# Hourly fixed windows, checked for every bucket before any is consumed, so a call
# denied by one bucket never burns budget in another. Returns seconds to wait, or 0.
RATE_SCRIPT = """
for i, key in ipairs(KEYS) do
  if tonumber(redis.call('GET', key) or '0') >= tonumber(ARGV[i]) then
    return math.max(redis.call('TTL', key), 1)
  end
end
for _, key in ipairs(KEYS) do
  if redis.call('INCR', key) == 1 then redis.call('EXPIRE', key, 3600) end
end
return 0
"""
_redis = None


def rate_limit_wait(connection):
    """Take one outbound call slot for this account, or return seconds until one frees."""
    global _redis
    if connection.is_test:
        return 0
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, socket_timeout=2, socket_connect_timeout=2)
    keys = [f"rate:{connection.provider}:{connection.pk}"]
    limits = [settings.CHANNEL_CALLS_PER_HOUR[connection.provider]]
    if connection.provider in META_PROVIDERS and settings.META_APP_CALLS_PER_HOUR:
        keys.append("rate:meta:app")
        limits.append(settings.META_APP_CALLS_PER_HOUR)
    return int(_redis.eval(RATE_SCRIPT, len(keys), *keys, *limits))


@shared_task(ignore_result=True)
def dispatch_channel_jobs():
    for wid, pk in ChannelConnection.all_objects.filter(status="verifying").values_list(
        "workspace_id", "pk"
    )[:50]:
        enqueue_once(verify_connection, wid, pk)
    for model, task in [(WebhookEvent, process_webhook), (Delivery, send_delivery)]:
        for workspace_id, pk in model.all_objects.filter(
            status="pending", available_at__lte=timezone.now()
        ).values_list("workspace_id", "pk")[:100]:
            enqueue_once(task, workspace_id, pk)
    # Never automatically retry an outbound request whose previous worker died
    # after claiming it: the provider may already have accepted that message.
    Delivery.all_objects.filter(
        status="sending", available_at__lt=timezone.now() - timedelta(minutes=5)
    ).update(status="unknown", error_code="worker_interrupted")


@shared_task(ignore_result=True)
@pause_guard("messaging")
def process_webhook(workspace_id, event_id):
    from apps.billing.gating import PlanLimitExceeded
    from apps.crm.services import receive

    with transaction.atomic():
        event = (
            WebhookEvent.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=event_id, status="pending", available_at__lte=timezone.now())
            .first()
        )
        if not event:
            return
        try:
            with transaction.atomic():
                receive(event, json.loads(event.payload))
        except PlanLimitExceeded:
            # Keep the inbound event durable while the workspace is at its cap.
            # Plan limits are not poison events and must not consume retry attempts.
            event.error_code = "plan_contact_limit"
            event.available_at = timezone.now() + timedelta(minutes=5)
            event.save(update_fields=["error_code", "available_at"])
            return
        except Exception as exc:
            # A poison event must not be retried every second forever or block others.
            event.attempts += 1
            event.error_code = type(exc).__name__[:50]
            if event.attempts >= MAX_WEBHOOK_ATTEMPTS:
                event.status = "failed"
            else:
                event.available_at = timezone.now() + timedelta(
                    seconds=min(3600, 10 * 4**event.attempts)
                )
            event.save(update_fields=["attempts", "error_code", "status", "available_at"])
            return
        event.status = "processed"
        event.processed_at = timezone.now()
        event.save(update_fields=["status", "processed_at"])


@shared_task(ignore_result=True)
@pause_guard("messaging")
def send_delivery(workspace_id, delivery_id):
    with transaction.atomic():
        item = (
            Delivery.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=delivery_id, status="pending", available_at__lte=timezone.now())
            .first()
        )
        if not item:
            return
        connection = item.connection
        if blocked(workspace_id, "messaging", "integration:" + connection.provider):
            return
        payload = json.loads(item.payload)
        if item.idempotency_key.startswith(("agent-reply:", "voice:")) and blocked(
            workspace_id, "ai"
        ):
            return
        automation_id = payload.get("automation_id")
        if item.idempotency_key.startswith("flow:"):
            if not automation_id:
                from uuid import UUID

                from apps.automations.models import ConversationState

                try:
                    state_id = UUID(item.idempotency_key.split(":")[1])
                except (ValueError, IndexError):
                    state_id = None
                if state_id:
                    automation_id = (
                        ConversationState.objects.for_workspace(workspace_id)
                        .filter(pk=state_id)
                        .values_list("automation_id", flat=True)
                        .first()
                    )
            if blocked(workspace_id, "automations", f"automation:{automation_id}"):
                return
        from apps.crm.models import Message
        from apps.crm.services import private_reply_sent, window_closed

        message = (
            Message.objects.for_workspace(workspace_id)
            .select_related("conversation__identity__lead")
            .filter(delivery=item)
            .first()
        )
        if message:
            # Policy is re-evaluated at send time: a delayed or rate-limited message must
            # not outlive the opt-in, window or private-reply allowance it was queued under.
            conversation = message.conversation
            from apps.automations.tracking import clicked

            private = bool(payload.get("private_reply"))
            if conversation.identity.lead.opted_out:
                reason = "opted_out"
            elif payload.get("unless_clicked") and clicked(workspace_id, payload["unless_clicked"]):
                reason = "link_already_clicked"
            elif private and private_reply_sent(
                workspace_id, connection, item.recipient_id, exclude=item.pk, in_flight=True
            ):
                reason = "private_reply_limit"
            elif (
                not private
                and payload.get("kind") != "public_comment"
                and window_closed(connection, conversation)
            ):
                reason = "messaging_window_closed"
            else:
                reason = ""
            if reason:
                item.status = "failed"
                item.error_code = reason
                item.save()
                audit(connection.workspace, None, "delivery.failed", item.pk)
                return
        if connection.status != "active" or connection.expires_at <= timezone.now():
            item.status = "failed"
            item.error_code = "connection_unavailable"
            item.save()
            return
        wait = rate_limit_wait(connection)
        if wait:
            item.available_at = timezone.now() + timedelta(seconds=wait + random.randint(0, 30))
            item.save()
            return
        item.status = "sending"
        item.attempts += 1
        item.available_at = timezone.now()
        item.save()
    try:
        adapter = adapter_for(connection)
        payload = json.loads(item.payload)
        if payload.get("kind") == "public_comment":
            message_id = adapter.reply_comment(
                comment_id=item.recipient_id,
                text=payload["text"],
                idempotency_key=item.idempotency_key,
            )
        elif payload.get("kind") == "media":
            from .media import validate_media

            validate_media(payload.get("media_url"), payload.get("media_type"))
            message_id = adapter.send_media(
                recipient_id=item.recipient_id,
                media_url=payload["media_url"],
                media_type=payload["media_type"],
                idempotency_key=item.idempotency_key,
            )
        elif payload.get("kind") == "voice":
            message_id = adapter.send_voice_note(
                recipient_id=item.recipient_id,
                media_url=payload["media_url"],
                idempotency_key=item.idempotency_key,
            )
        else:
            kwargs = {
                "recipient_id": item.recipient_id,
                "text": payload["text"],
                "idempotency_key": item.idempotency_key,
            }
            if not connection.is_test and connection.provider in {"instagram", "messenger"}:
                kwargs.update(
                    buttons=payload.get("buttons"),
                    private_reply=payload.get("private_reply", False),
                )
            elif not connection.is_test and connection.provider in {"telegram", "whatsapp"}:
                kwargs["buttons"] = payload.get("buttons")
            message_id = adapter.send_message(**kwargs)
        if not message_id:
            raise AmbiguousDelivery()
    except RetryableError as exc:
        item.status = "pending" if item.attempts < 8 else "failed"
        item.error_code = exc.code
        item.available_at = timezone.now() + timedelta(
            seconds=max(exc.delay, min(3600, 2**item.attempts)) + random.randint(0, 5)
        )
    except AmbiguousDelivery:
        item.status = "unknown"
        item.error_code = "delivery_unknown"
    except (ProviderError, IntegrationUnavailable, ValidationError) as exc:
        item.status = "failed"
        item.error_code = getattr(exc, "code", "integration_disabled")
    else:
        item.status = "sent"
        item.provider_message_id = str(message_id)
        item.sent_at = timezone.now()
    with transaction.atomic():
        item.save()
        audit(connection.workspace, None, "delivery." + item.status, item.id)
        if item.status == "sent":
            from apps.public_api.services import emit

            emit(
                workspace_id,
                "message.sent",
                {
                    "delivery_id": str(item.id),
                    "recipient_id": item.recipient_id,
                    "provider_message_id": item.provider_message_id,
                    "provider": connection.provider,
                },
            )


@shared_task(ignore_result=True)
def refresh_expiring_tokens():
    for workspace_id, pk in ChannelConnection.all_objects.filter(
        provider="instagram", status="active", refresh_due_at__lte=timezone.now()
    ).values_list("workspace_id", "pk")[:100]:
        enqueue_once(refresh_connection, workspace_id, pk, ttl=300)


@shared_task(ignore_result=True)
@pause_guard("integration:instagram")
def refresh_connection(workspace_id, connection_id):
    with transaction.atomic():
        connection = (
            ChannelConnection.objects.for_workspace(workspace_id)
            .select_for_update()
            .get(pk=connection_id)
        )
        if connection.refresh_due_at and connection.refresh_due_at > timezone.now():
            return
        try:
            credentials = adapter_for(connection).refresh_token(
                Credentials(
                    connection.external_account_id,
                    connection.display_name,
                    connection.access_token,
                    connection.expires_at,
                )
            )
        except RetryableError as exc:
            connection.refresh_due_at = timezone.now() + timedelta(seconds=exc.delay)
        except (ProviderError, IntegrationUnavailable):
            connection.status = "reconnect_required"
            audit(connection.workspace, None, "channel.reconnect_required", connection.id)
        else:
            connection.access_token = credentials.access_token
            connection.expires_at = credentials.expires_at
            connection.last_refreshed_at = timezone.now()
            connection.refresh_due_at = credentials.expires_at - timedelta(days=7)
            audit(connection.workspace, None, "channel.token_refreshed", connection.id)
        connection.save()


@shared_task(ignore_result=True)
@pause_guard()
def verify_connection(workspace_id, connection_id):
    from .transport import request

    with transaction.atomic():
        connection = (
            ChannelConnection.objects.for_workspace(workspace_id)
            .select_for_update()
            .get(pk=connection_id)
        )
        if connection.status != "verifying":
            return
        if blocked(workspace_id, "integration:" + connection.provider):
            return
        try:
            if connection.provider == "telegram":
                adapter = adapter_for(connection)
                profile = adapter.call("getMe", {})
                if str(profile["id"]) != connection.external_account_id:
                    raise ValueError("account_mismatch")
                if not settings.PUBLIC_APP_URL.startswith("https://"):
                    raise ValueError("public_https_required")
                adapter.configure_webhook(
                    settings.PUBLIC_APP_URL + f"/webhooks/telegram/{connection.pk}/"
                )
            else:
                fields = (
                    "id,name" if connection.provider == "messenger" else "id,display_phone_number"
                )
                profile = request(
                    "GET",
                    f"https://graph.facebook.com/{settings.META_API_VERSION}/{connection.external_account_id}",
                    headers={"Authorization": f"Bearer {connection.access_token}"},
                    params={"fields": fields},
                )
                if connection.provider == "messenger":
                    # Subscribe the Page to messaging webhooks for this app.
                    request(
                        "POST",
                        f"https://graph.facebook.com/{settings.META_API_VERSION}/{connection.external_account_id}/subscribed_apps",
                        headers={"Authorization": f"Bearer {connection.access_token}"},
                        data={"subscribed_fields": "messages,messaging_postbacks"},
                    )
                if str(profile["id"]) != connection.external_account_id:
                    raise ValueError("account_mismatch")
        except (ProviderError, IntegrationUnavailable, ValueError, KeyError):
            connection.status = "reconnect_required"
        else:
            connection.status = "active"
        connection.save()
