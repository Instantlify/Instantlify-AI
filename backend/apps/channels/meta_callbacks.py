"""Meta platform callbacks required for App Review.

Both receive a `signed_request` (base64url signature + payload, HMAC-SHA256 with the
app secret). Deauthorize: the person removed the app, so their connected accounts are
disconnected and tokens wiped. Data deletion: the same, plus a confirmation code and a
public status URL, as Meta requires. Customer conversations a workspace collected stay
with that workspace (it is the controller); the workspace owner can delete them.
"""

import base64
import hashlib
import hmac
import json
import secrets

from django.conf import settings
from django.db import transaction
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
    if not data.get("user_id"):
        return None
    return data


def _disconnect(user_id):
    """Disconnect and wipe every Meta connection owned by this Meta user."""
    from apps.tenants.services import audit

    cleared = 0
    with transaction.atomic():
        for connection in ChannelConnection.all_objects.select_for_update().filter(
            provider__in=["instagram", "messenger"], external_account_id=str(user_id)
        ):
            connection.status = "disconnected"
            connection.access_token = ""
            connection.webhook_secret = ""
            connection.profile = {}
            connection.save()
            audit(connection.workspace, None, "channel.meta_deauthorized", connection.id)
            cleared += 1
    return cleared


def _signed(request):
    return parse_signed_request(request.POST.get("signed_request", ""), settings.META_APP_SECRET)


@csrf_exempt
def meta_deauthorize(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    data = _signed(request)
    if data is None:
        return HttpResponse(status=400)
    _disconnect(data["user_id"])
    return HttpResponse(status=200)


@csrf_exempt
def meta_data_deletion(request):
    from .models import MetaDataDeletion

    if request.method != "POST":
        return HttpResponse(status=405)
    data = _signed(request)
    if data is None:
        return HttpResponse(status=400)
    cleared = _disconnect(data["user_id"])
    record = MetaDataDeletion.objects.create(
        code=secrets.token_urlsafe(12),
        user_hash=hashlib.sha256(str(data["user_id"]).encode()).hexdigest(),
        connections_cleared=cleared,
    )
    return JsonResponse(
        {
            "url": f"{settings.PUBLIC_APP_URL.rstrip('/')}/data-deletion/?code={record.code}",
            "confirmation_code": record.code,
        }
    )


def data_deletion_status(request, code):
    from .models import MetaDataDeletion

    record = MetaDataDeletion.objects.filter(code=code[:40]).first()
    if record is None:
        return JsonResponse({"detail": "Unknown confirmation code."}, status=404)
    return JsonResponse(
        {
            "confirmation_code": record.code,
            "status": "completed",
            "requested_at": record.created_at.isoformat(),
            "connections_disconnected": record.connections_cleared,
        }
    )
