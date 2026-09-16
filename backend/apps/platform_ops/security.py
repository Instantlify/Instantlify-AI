import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Control, PlatformAudit, PlatformRole


def record(actor, action, workspace="", **detail):
    return PlatformAudit.objects.create(
        actor_id=str(getattr(actor, "pk", actor)),
        action=action,
        workspace_id=str(workspace),
        detail=detail,
    )


def blocked(workspace, *keys):
    return Control.objects.filter(
        scope__in=["", str(workspace)], key__in=["workspace", *keys], disabled=True
    ).exists()


def assert_enabled(workspace, *keys):
    from apps.channels.transport import ProviderError

    if blocked(workspace, *keys):
        raise ProviderError("platform_paused")


def pause_guard(*keys):
    from functools import wraps

    def decorate(task):
        @wraps(task)
        def wrapped(workspace_id, *args, **kwargs):
            if blocked(workspace_id, *keys):
                return
            from .metrics import workspace_metrics

            with workspace_metrics(workspace_id):
                return task(workspace_id, *args, **kwargs)

        return wrapped

    return decorate


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode()


def code_at(secret, counter):
    digest = hmac.new(base64.b32decode(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return f"{(struct.unpack('>I', digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"


@transaction.atomic
def verify_otp(pk, code):
    role = PlatformRole.objects.select_for_update().get(pk=pk)
    now = timezone.now()
    if role.locked_until and role.locked_until > now:
        return False
    current = int(time.time()) // 30
    for counter in [current - 1, current, current + 1]:
        if (
            role.otp_secret
            and counter > role.last_counter
            and hmac.compare_digest(code_at(role.otp_secret, counter), str(code))
        ):
            role.last_counter = counter
            role.failed_attempts = 0
            role.locked_until = None
            role.otp_confirmed = True
            role.save()
            return True
    role.failed_attempts += 1
    if role.failed_attempts >= 5:
        role.locked_until = now + timedelta(minutes=15)
    role.save(update_fields=["failed_attempts", "locked_until"])
    record(role.user, "platform.otp_rejected")
    return False
