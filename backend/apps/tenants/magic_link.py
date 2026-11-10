"""Passwordless sign-in by emailed link.

The token is signed, expires after 15 minutes, and embeds the user's last login time,
so it stops working the moment it is used (signing in updates last_login). The link
puts the token in the URL fragment so it never reaches server or proxy logs, and the
request endpoint answers identically whether or not the email has an account.
"""

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.core import signing
from django.core.mail import send_mail
from rest_framework import serializers
from rest_framework.response import Response

from .views import SignupView

SALT = "nemio.magic-link"
MAX_AGE = 15 * 60


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
        user = (
            get_user_model()
            .objects.filter(
                email__iexact=serializer.validated_data["email"], is_active=True, is_banned=False
            )
            .first()
        )
        if user:
            url = f"{settings.PUBLIC_APP_URL}/auth/magic/#token={make_token(user)}"
            send_mail(
                "Your Nemio sign-in link",
                f"Use this link within 15 minutes to sign in:\n\n{url}\n\n"
                "It works once. If you did not ask for it, you can ignore this email.",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=True,
            )
        return Response({"detail": "If this email has an account, a sign-in link is on its way."})


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
