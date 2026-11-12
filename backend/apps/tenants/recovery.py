"""Email-based recovery with expiring, single-use Django password reset tokens."""

import logging
from smtplib import SMTPException

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import BadHeaderError
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.platform_ops.growth import TemplateMissing, send_transactional_email

from .views import SignupView

log = logging.getLogger(__name__)


class RecoveryRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class RecoveryConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=100)
    token = serializers.CharField(max_length=200)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class PasswordResetRequestView(SignupView):
    def post(self, request):
        serializer = RecoveryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = (
            get_user_model()
            .objects.filter(
                email__iexact=serializer.validated_data["email"], is_active=True, is_banned=False
            )
            .first()
        )
        if user and user.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            # A fragment keeps the reset secret out of HTTP/access logs and referrers.
            url = f"{settings.PUBLIC_APP_URL.rstrip('/')}/auth/reset/#uid={uid}&token={token}"
            try:
                send_transactional_email(
                    "password-reset",
                    user.email,
                    {"name": user.first_name or "there", "email": user.email, "link": url},
                )
            except (SMTPException, OSError, BadHeaderError, TemplateMissing):
                log.error(
                    "Password-reset email was not sent",
                    extra={"event_code": "password_reset_email_failed"},
                )
        return Response(
            {"detail": "If this email has an eligible account, a reset link is on its way."}
        )


class PasswordResetConfirmView(SignupView):
    @transaction.atomic
    def post(self, request):
        serializer = RecoveryConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            uid = urlsafe_base64_decode(data["uid"]).decode()
            user = (
                get_user_model()
                .objects.select_for_update()
                .get(pk=uid, is_active=True, is_banned=False)
            )
        except (ValueError, UnicodeDecodeError, OverflowError, get_user_model().DoesNotExist):
            user = None
        if not user or not default_token_generator.check_token(user, data["token"]):
            return Response(
                {"detail": "This reset link is invalid or expired. Request a new one."}, status=400
            )
        try:
            validate_password(data["password"], user)
        except ValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        user.set_password(data["password"])
        user.save(update_fields=["password"])
        # Django sessions invalidate on password hash changes; revoke API refresh tokens too.
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        return Response({"detail": "Password updated. Sign in with your new password."})
