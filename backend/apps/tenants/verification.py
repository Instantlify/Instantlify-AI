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

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response

from .views import SignupView

SALT = "tenants.email-verification"
MAX_AGE = 60 * 60 * 24 * 3


def make_token(user):
    return signing.dumps({"user": str(user.pk), "email": user.email.casefold()}, salt=SALT)


def send_verification(user):
    """Best effort, like the welcome mail: a bounced message must not fail a signup."""
    if user.email_verified_at:
        return
    url = f"{settings.PUBLIC_APP_URL}/auth/verify/#token={make_token(user)}"
    send_mail(
        "Confirm your Instantlify email address",
        f"Confirm this address to finish setting up your account:\n\n{url}\n\n"
        "The link expires in three days. If you did not sign up, you can ignore this email.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=True,
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
