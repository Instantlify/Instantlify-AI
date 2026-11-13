"""Verified Meta revocation and deletion requests with truthful asynchronous status."""

import base64
import hashlib
import hmac
import json
import secrets

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import ChannelConnection


def _b64decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def parse_signed_request(signed, secret):
    """The payload dict, or None when the signature or format is wrong."""
    if not secret or not isinstance(signed, str) or signed.count(".") != 1:
        return None
    signature, payload = signed.split(".", 1)
    try:
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64decode(signature), expected):
            return None
        data = json.loads(_b64decode(payload))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or str(data.get("algorithm", "")).upper() != "HMAC-SHA256":
        return None
    user_id = data.get("user_id")
    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, (str, int))
        or not str(user_id).isdigit()
        or len(str(user_id)) > 200
    ):
        return None
    data["user_id"] = str(user_id)
    return data


def matching_connections(user_id, providers):
    return ChannelConnection.all_objects.filter(provider__in=providers).filter(
        Q(meta_authorizer_id=str(user_id))
        | Q(provider="instagram", external_account_id=str(user_id))
    )


def _disconnect(user_id, providers):
    """Disconnect and wipe every Meta connection owned by this Meta user."""
    from apps.tenants.services import audit

    cleared = 0
    with transaction.atomic():
        for connection in matching_connections(user_id, providers).select_for_update():
            connection.status = "disconnected"
            connection.access_token = ""
            connection.webhook_secret = ""
            connection.profile = {}
            connection.save()
            audit(connection.workspace, None, "channel.meta_deauthorized", connection.id)
            cleared += 1
    return cleared


def _signed(request):
    signed = request.POST.get("signed_request", "")
    if not isinstance(signed, str) or len(signed) > 16384:
        return None, set()
    providers, verified = set(), None
    for secret, allowed in [
        (settings.META_APP_SECRET, {"instagram"}),
        (settings.MESSENGER_APP_SECRET, {"messenger"}),
        (settings.WHATSAPP_APP_SECRET, {"whatsapp"}),
    ]:
        data = parse_signed_request(signed, secret)
        if data is not None:
            verified = data
            providers.update(allowed)
    return verified, providers


@csrf_exempt
def meta_deauthorize(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    data, providers = _signed(request)
    if data is None:
        return HttpResponse(status=400)
    _disconnect(data["user_id"], providers)
    return HttpResponse(status=200)


@csrf_exempt
def meta_data_deletion(request):
    from .models import MetaDataDeletion

    if request.method != "POST":
        return HttpResponse(status=405)
    data, providers = _signed(request)
    if data is None:
        return HttpResponse(status=400)
    fingerprint = hashlib.sha256(request.POST["signed_request"].encode()).hexdigest()
    with transaction.atomic():
        record, created = MetaDataDeletion.objects.get_or_create(
            request_hash=fingerprint,
            defaults={
                "code": secrets.token_hex(16),
                "user_hash": hashlib.sha256(data["user_id"].encode()).hexdigest(),
                "subject_id": data["user_id"],
                "providers": sorted(providers),
                "status": "pending",
            },
        )
        if created:
            record.connection_ids = [
                str(pk)
                for pk in matching_connections(data["user_id"], providers)
                .select_for_update()
                .values_list("pk", flat=True)
            ]
            record.connections_cleared = _disconnect(data["user_id"], providers)
            record.save(update_fields=["connection_ids", "connections_cleared"])
    return JsonResponse(
        {
            "url": f"{settings.PUBLIC_APP_URL.rstrip('/')}/data-deletion/?code={record.code}",
            "confirmation_code": record.code,
        }
    )


def data_deletion_status(request, code):
    from .models import MetaDataDeletion

    if request.method not in {"GET", "HEAD"}:
        return HttpResponse(status=405)
    record = MetaDataDeletion.objects.filter(code=code).first() if 1 <= len(code) <= 40 else None
    if record is None:
        return JsonResponse({"detail": "Unknown confirmation code."}, status=404)
    response = JsonResponse(
        {
            "confirmation_code": record.code,
            "status": record.status,
            "requested_at": record.created_at.isoformat(),
            "connections_disconnected": record.connections_cleared,
            "connections_deleted": record.connections_deleted,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }
    )

    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response
