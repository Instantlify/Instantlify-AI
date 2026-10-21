import hmac
import json

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import ChannelConnection, WebhookEvent
from .signatures import verify_meta_signature


def normalize_meta(payload, provider):
    """Routing/dedupe envelopes only. No CRM, media, or AI work in the receiver."""
    for entry in payload.get("entry", []):
        account_id = str(entry.get("id", ""))
        if provider in {"instagram", "messenger"}:
            for event in entry.get("messaging", []):
                message = event.get("message", {})
                postback = event.get("postback", {})
                if message.get("is_echo") or not (message.get("mid") or postback.get("mid")):
                    continue
                yield (
                    account_id,
                    message.get("mid") or postback["mid"],
                    {
                        "sender_id": str(event["sender"]["id"]),
                        "text": message.get("text", postback.get("payload", "")),
                        "kind": "story_reply" if message.get("reply_to", {}).get("story") else "dm",
                        "attachments": message.get("attachments", []),
                        "timestamp": event.get("timestamp"),
                    },
                )
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if provider == "instagram" and change.get("field") in {"comments", "live_comments"}:
                yield (
                    account_id,
                    "comment:" + str(value["id"]),
                    {
                        "sender_id": str(value["from"]["id"]),
                        "text": value.get("text", ""),
                        "kind": "live_comment" if change["field"] == "live_comments" else "comment",
                        "comment_id": str(value["id"]),
                        "attachments": [],
                    },
                )
            if (
                provider == "messenger"
                and change.get("field") == "feed"
                and value.get("item") == "comment"
                and value.get("verb") == "add"
                # The Page's own replies arrive on the same feed; never answer ourselves.
                and str(value.get("from", {}).get("id", "")) not in {"", account_id}
            ):
                yield (
                    account_id,
                    "comment:" + str(value["comment_id"]),
                    {
                        "sender_id": str(value["from"]["id"]),
                        "text": value.get("message", ""),
                        "kind": "comment",
                        "comment_id": str(value["comment_id"]),
                        "attachments": [],
                    },
                )
            if provider == "whatsapp":
                account_id = str(value.get("metadata", {}).get("phone_number_id", ""))
                for message in value.get("messages", []):
                    yield (
                        account_id,
                        message["id"],
                        {
                            "sender_id": message["from"],
                            "text": message.get("text", {}).get("body", ""),
                            "kind": "dm",
                            "attachments": [{"type": "audio", "media_id": message["audio"]["id"]}]
                            if "audio" in message
                            else [],
                        },
                    )


@transaction.atomic
def persist_events(provider, envelopes):
    count = 0
    for account_id, event_id, normalized in envelopes:
        count += 1
        if count > 250:
            raise ValueError("Webhook batch too large")
        connection = ChannelConnection.all_objects.filter(
            provider=provider, external_account_id=account_id, status="active"
        ).first()
        if not connection:
            continue
        WebhookEvent.objects.for_workspace(connection.workspace_id).get_or_create(
            connection=connection,
            event_id=str(event_id),
            defaults={
                "workspace_id": connection.workspace_id,
                "payload": json.dumps(normalized),
                "available_at": timezone.now(),
            },
        )
    # Polling a durable DB queue is deliberately independent of broker availability.
    return count


APP_SECRETS = {
    "instagram": "META_APP_SECRET",
    "whatsapp": "WHATSAPP_APP_SECRET",
    "messenger": "MESSENGER_APP_SECRET",
}


@csrf_exempt
def meta_webhook(request, provider):
    if provider not in APP_SECRETS:
        return HttpResponse(status=404)
    if request.method == "GET":
        token = request.GET.get("hub.verify_token", "")
        if (
            settings.META_WEBHOOK_VERIFY_TOKEN
            and request.GET.get("hub.mode") == "subscribe"
            and hmac.compare_digest(token, settings.META_WEBHOOK_VERIFY_TOKEN)
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponse(status=403)
    if request.method != "POST":
        return HttpResponse(status=405)
    body = request.body
    if not verify_meta_signature(
        body,
        request.headers.get("X-Hub-Signature-256"),
        getattr(settings, APP_SECRETS[provider]),
    ):
        return HttpResponse(status=403)
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError()
        persist_events(provider, normalize_meta(payload, provider))
    except (ValueError, KeyError, TypeError, AttributeError):
        return JsonResponse({"detail": "Invalid webhook payload"}, status=400)
    return HttpResponse(status=200)


@csrf_exempt
def telegram_webhook(request, connection_id):
    if request.method != "POST":
        return HttpResponse(status=405)
    connection = ChannelConnection.all_objects.filter(
        pk=connection_id, provider="telegram", status="active"
    ).first()
    if (
        not connection
        or not connection.webhook_secret
        or not hmac.compare_digest(
            request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), connection.webhook_secret
        )
    ):
        return HttpResponse(status=403)
    try:
        payload = json.loads(request.body)
        message = payload.get("message") or payload.get("callback_query", {}).get("message")
        if message:
            persist_events(
                "telegram",
                [
                    (
                        connection.external_account_id,
                        str(payload["update_id"]),
                        {
                            "sender_id": str(message["chat"]["id"]),
                            "text": payload.get("callback_query", {}).get("data")
                            or message.get("text", ""),
                            "kind": "dm",
                            "attachments": [
                                {"type": "audio", "media_id": message["voice"]["file_id"]}
                            ]
                            if "voice" in message
                            else [],
                        },
                    )
                ],
            )
    except (ValueError, KeyError, TypeError, AttributeError):
        return HttpResponse(status=400)
    return HttpResponse(status=200)


@csrf_exempt
def linkedin_webhook(request):
    if request.method == "GET":
        challenge = request.GET.get("challengeCode", "")
        if challenge:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse(status=200)
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        payload = json.loads(request.body)
        events = []
        elements = (
            payload.get("elements") if isinstance(payload.get("elements"), list) else [payload]
        )
        for entry in elements:
            account_id = str(
                entry.get("organization") or entry.get("recipient") or "urn:li:organization:123456"
            )
            event_id = str(
                entry.get("id") or entry.get("eventId") or entry.get("timestamp") or "li-ev-1"
            )
            sender = str(entry.get("sender") or entry.get("actor") or "urn:li:person:lead")
            text = str(
                entry.get("text")
                or entry.get("message", {}).get("text")
                or entry.get("comment", {}).get("text")
                or ""
            )
            kind = "comment" if "comment" in str(entry.get("type", "")).lower() else "dm"
            events.append(
                (
                    account_id,
                    event_id,
                    {
                        "sender_id": sender,
                        "text": text,
                        "kind": kind,
                        "attachments": [],
                    },
                )
            )
        if events:
            persist_events("linkedin", events)
    except (ValueError, KeyError, TypeError, AttributeError):
        return HttpResponse(status=400)
    return HttpResponse(status=200)


@csrf_exempt
def snapchat_webhook(request):
    from datetime import timedelta

    from apps.crm.models import ChannelIdentity, Conversation, Lead, Message
    from apps.tenants.models import Workspace

    if request.method == "GET":
        challenge = request.GET.get("challenge", "")
        if challenge:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse(status=200)
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        payload = json.loads(request.body)
        workspace_id = request.GET.get("workspace_id")
        workspace = None
        if workspace_id:
            workspace = Workspace.objects.filter(pk=workspace_id).first()
        if not workspace:
            workspace = Workspace.objects.first()
        if not workspace:
            return HttpResponse(status=404)

        lead_data = payload.get("form_data") or payload.get("data") or payload
        email = str(lead_data.get("email") or lead_data.get("email_address") or "").strip()
        name = str(lead_data.get("name") or lead_data.get("full_name") or "Snapchat Lead").strip()
        phone = str(lead_data.get("phone") or lead_data.get("phone_number") or "").strip()
        sender_id = str(
            payload.get("lead_id") or payload.get("submission_id") or email or phone or "snap_user"
        )

        with transaction.atomic():
            connection, _ = ChannelConnection.objects.for_workspace(workspace).get_or_create(
                workspace=workspace,
                provider="snapchat",
                external_account_id="snapchat-lead-ads",
                defaults={
                    "display_name": "Snapchat Lead Ads",
                    "access_token": "snapchat-lead-token",
                    "expires_at": timezone.now() + timedelta(days=3650),
                    "status": "active",
                    "is_test": False,
                },
            )
            lead = (
                Lead.objects.for_workspace(workspace).filter(email=email).first() if email else None
            )
            if not lead:
                lead = Lead.objects.for_workspace(workspace).create(
                    workspace=workspace,
                    name=name,
                    email=email,
                    stage="new",
                    tags=["snapchat", "lead_ad"],
                    fields={"phone": phone} if phone else {},
                )
            identity, _ = ChannelIdentity.objects.for_workspace(workspace).get_or_create(
                workspace=workspace,
                connection=connection,
                external_id=sender_id,
                defaults={"lead": lead},
            )
            conv, _ = Conversation.objects.for_workspace(workspace).get_or_create(
                workspace=workspace,
                identity=identity,
                defaults={"status": "open"},
            )
            Message.objects.for_workspace(workspace).create(
                workspace=workspace,
                conversation=conv,
                direction="inbound",
                kind="dm",
                text=f"[Snapchat Lead Ad submission] Name: {name}, Email: {email}, Phone: {phone}",
            )
    except Exception:
        return HttpResponse(status=400)
    return HttpResponse(status=200)
