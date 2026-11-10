"""Sign in (or sign up) with Google.

Standard OAuth 2.0 authorization-code flow with a per-session random state. Only a
Google-verified email is trusted. An existing account with that email signs in; a new
email creates an account with no password (it can set one later through reset) and a
verified email. Disabled until GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set.
"""

import hmac
import secrets
import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework.response import Response

from apps.channels.transport import ProviderError
from apps.channels.transport import request as http_request

from .views import SignupView

SESSION_KEY = "google_login_state"


def enabled():
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def redirect_uri():
    return getattr(settings, "GOOGLE_LOGIN_REDIRECT_URI", "") or (
        settings.PUBLIC_APP_URL.rstrip("/") + "/api/auth/google/callback/"
    )


def _back(error=""):
    target = settings.PUBLIC_APP_URL.rstrip("/") + "/auth/"
    return HttpResponseRedirect(target + (f"?google_error={error}" if error else ""))


class GoogleLoginStatusView(SignupView):
    def get(self, request):
        return Response({"enabled": enabled()})


class GoogleLoginStartView(SignupView):
    def get(self, request):
        if not enabled():
            return _back("not_configured")
        state = secrets.token_urlsafe(32)
        request.session[SESSION_KEY] = state
        query = urlencode(
            {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "redirect_uri": redirect_uri(),
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "prompt": "select_account",
            }
        )
        return HttpResponseRedirect("https://accounts.google.com/o/oauth2/v2/auth?" + query)


class GoogleLoginCallbackView(SignupView):
    def get(self, request):
        expected = request.session.pop(SESSION_KEY, "")
        state = request.query_params.get("state", "")
        code = request.query_params.get("code", "")
        if not enabled():
            return _back("not_configured")
        if not expected or not hmac.compare_digest(expected, state) or not code:
            return _back("invalid_state")
        try:
            tokens = request_tokens(code)
            profile = http_request(
                "GET",
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
        except (ProviderError, KeyError, TypeError):
            return _back("google_rejected")
        email = str(profile.get("email") or "").strip().lower()
        if not email or profile.get("email_verified") is not True:
            return _back("email_not_verified")
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user and (not user.is_active or user.is_banned):
            return _back("account_unavailable")
        if user is None:
            try:
                with transaction.atomic():
                    user = get_user_model().objects.create_user(
                        username=str(uuid.uuid4()),
                        email=email,
                        first_name=str(profile.get("name") or "")[:150],
                        password=None,
                    )
                    user.email_verified_at = timezone.now()
                    user.save(update_fields=["email_verified_at"])
            except IntegrityError:
                return _back("account_unavailable")
        elif not user.email_verified_at:
            # Google has verified this address, which is what verification proves.
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])
        login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
        return _back()


def request_tokens(code):
    return http_request(
        "POST",
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        },
    )
