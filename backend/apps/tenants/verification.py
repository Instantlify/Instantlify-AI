"""Proof that a signup controls the address it claimed.

Without it anyone can hold an account under someone else's address, password-reset
mail goes to unconfirmed mailboxes, and the signup grant in `billing.credits` pays
provider bills for addresses nobody owns. Verification is what makes that grant
safe to hand out, so `grant_signup_credit` is called from here.

The link carries a signed payload rather than a database row: it expires on its own,
and binding the address into the signature means a link stops working the moment the
account moves to a different one. Re-verifying an already verified account is a no-op,
so a replayed link is harmless and no single-use bookkeeping is needed.
"""

import logging
from smtplib import SMTPException

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import BadHeaderError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response

from apps.platform_ops.growth import TemplateMissing, send_transactional_email

from .views import SignupView

SALT = "tenants.email-verification"
MAX_AGE = 60 * 60 * 24 * 3
log = logging.getLogger(__name__)


def make_token(user):
    return signing.dumps({"user": str(user.pk), "email": user.email.casefold()}, salt=SALT)


def send_verification(user, *, template_name="email-verification"):
    """Best effort, like the welcome mail: a bounced message must not fail a signup."""
    if user.email_verified_at:
        return
    url = f"{settings.PUBLIC_APP_URL.rstrip('/')}/auth/verify/#token={make_token(user)}"
    try:
        send_transactional_email(
            template_name,
            user.email,
            {"name": user.first_name or "there", "email": user.email, "link": url},
        )
    except (SMTPException, OSError, BadHeaderError, TemplateMissing):
        log.error(
            "Verification email was not sent", extra={"event_code": "verification_email_failed"}
        )


def send_email_change_notice(user, old_email):
    try:
        send_transactional_email(
            "email-change-notice-current",
            old_email,
            {
                "name": user.first_name or "there",
                "new_email": user.email,
                "support_email": "support@instantlify.com",
            },
        )
    except (SMTPException, OSError, BadHeaderError, TemplateMissing):
        log.error(
            "Email-change notice was not sent", extra={"event_code": "email_change_notice_failed"}
        )


class ConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=500)


class ResendSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class VerifyEmailView(SignupView):
    @transaction.atomic
    def post(self, request):
        serializer = ConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            data = signing.loads(serializer.validated_data["token"], salt=SALT, max_age=MAX_AGE)
        except signing.BadSignature:
            return Response(
                {"detail": "This confirmation link is invalid or expired. Request a new one."},
                status=400,
            )
        user = (
            get_user_model()
            .objects.select_for_update()
            .filter(pk=data["user"], is_active=True, is_banned=False)
            .first()
        )
        # The address is part of the signature, so a link issued for a previous address
        # cannot confirm the current one.
        if not user or user.email.casefold() != data["email"]:
            return Response(
                {"detail": "This confirmation link is invalid or expired. Request a new one."},
                status=400,
            )
        if not user.email_verified_at:
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])
            grant_signup_credit(user)
        return Response({"detail": "Email confirmed.", "email": user.email})


class ResendVerificationView(SignupView):
    def post(self, request):
        serializer = ResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = (
            get_user_model()
            .objects.filter(
                email__iexact=serializer.validated_data["email"], is_active=True, is_banned=False
            )
            .first()
        )
        if user:
            send_verification(user)
        # Same answer either way, so this cannot be used to discover who has an account.
        return Response({"detail": "If that address needs confirming, a new link is on its way."})


def grant_signup_credit(user):
    """Credit every workspace this user owns, once each. Called on verification because
    a workspace is usually created before the address is confirmed."""
    from apps.billing.credits import grant_signup_credit as grant

    from .models import Membership

    owned = Membership.all_objects.filter(user=user, role=Membership.Role.OWNER).values_list(
        "workspace_id", flat=True
    )
    for workspace_id in owned:
        grant(workspace_id)
