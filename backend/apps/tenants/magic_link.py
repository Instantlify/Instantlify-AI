"""Passwordless sign-in by emailed link.

The token is signed, expires after 15 minutes, and embeds the user's last login time,
so it stops working the moment it is used (signing in updates last_login). The link
puts the token in the URL fragment so it never reaches server or proxy logs, and the
request endpoint answers identically whether or not the email has an account.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.core import signing
from django.core.cache import cache
from django.utils.crypto import salted_hmac
from rest_framework import serializers
from rest_framework.response import Response

from .views import SignupView

SALT = "nemio.magic-link"
MAX_AGE = 15 * 60
RESEND_SECONDS = 60
log = logging.getLogger(__name__)
REQUEST_DETAIL = (
    "If an account exists for this email address, you'll receive a sign-in link shortly. "
    "Please check your inbox and spam folder."
)


def _stamp(user):
    return user.last_login.isoformat() if user.last_login else ""


def make_token(user):
    return signing.dumps({"u": user.pk, "l": _stamp(user)}, salt=SALT)


def user_for_token(token):
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        return None
    user = (
        get_user_model().objects.filter(pk=data.get("u"), is_active=True, is_banned=False).first()
    )
    if not user or data.get("l") != _stamp(user):
        return None
    return user


class MagicLinkRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class MagicLinkTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=500)


class MagicLinkRequestView(SignupView):
    def post(self, request):
        serializer = MagicLinkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .tasks import deliver_magic_link

        if settings.EMAIL_BACKEND in {
            "django.core.mail.backends.console.EmailBackend",
            "django.core.mail.backends.dummy.EmailBackend",
        }:
            log.error(
                "Magic-link email backend is not configured for delivery",
                extra={"event_code": "magic_link_backend_unavailable"},
            )
            return Response(
                {
                    "detail": "Sign-in links are temporarily unavailable. Please sign in with your password."
                },
                status=503,
            )
        email = serializer.validated_data["email"].strip().lower()
        key = "magic-link-resend:" + salted_hmac("magic-link-resend", email).hexdigest()
        if cache.add(key, True, timeout=RESEND_SECONDS):
            user = (
                get_user_model()
                .objects.filter(email__iexact=email, is_active=True, is_banned=False)
                .first()
            )
            try:
                # Enqueue for unknown addresses too: response and broker-error behavior
                # must not reveal whether an account exists. No email is sent for them.
                deliver_magic_link.delay(user.pk if user else None)
            except Exception:  # broker failure, never claim a queued request succeeded
                cache.delete(key)
                log.error(
                    "Magic-link email could not be queued",
                    extra={"event_code": "magic_link_queue_failed"},
                )
                return Response(
                    {
                        "detail": "Sign-in links are temporarily unavailable. Please try again shortly or sign in with your password."
                    },
                    status=503,
                )
        return Response({"detail": REQUEST_DETAIL, "resend_after": RESEND_SECONDS})


class MagicLinkVerifyView(SignupView):
    def post(self, request):
        serializer = MagicLinkTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = user_for_token(serializer.validated_data["token"])
        if user is None:
            return Response(
                {"detail": "This sign-in link is invalid, used or expired. Request a new one."},
                status=400,
            )
        login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
        return Response(
            {
                "id": user.id,
                "name": user.first_name,
                "email": user.email,
                "email_verified": bool(user.email_verified_at),
            }
        )
