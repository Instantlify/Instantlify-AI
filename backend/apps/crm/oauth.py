"""Hosted OAuth for tenant integrations (Google Calendar, Slack).

Mirrors the Meta channel flow: a user-bound, hashed, single-use state row; the
callback re-checks membership; tokens are stored encrypted on IntegrationConfig
and never returned to the browser. With no provider app configured, local fake
mode offers a test integration so the UI flow stays exercisable offline.
"""

import hashlib
import json
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.channels.models import OAuthState
from apps.channels.transport import ProviderError, request
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import IntegrationConfig

LOCAL_CODE = "local-test-code"

PROVIDERS = {
    "google_sheets": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "client": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
        "params": {
            "scope": "https://www.googleapis.com/auth/spreadsheets",
            "access_type": "offline",
            "prompt": "consent",
        },
    },
    "gmail": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "client": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
        "params": {
            "scope": "openid email https://www.googleapis.com/auth/gmail.send",
            "access_type": "offline",
            "prompt": "consent",
        },
    },
    "google_calendar": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "client": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
        "params": {
            "scope": "https://www.googleapis.com/auth/calendar.events "
            "https://www.googleapis.com/auth/calendar.readonly",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        },
    },
    "slack": {
        "authorize": "https://slack.com/oauth/v2/authorize",
        "client": ("SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET"),
        # incoming-webhook lets the installer pick the channel during install, so no
        # channel ID has to be typed in afterwards.
        "params": {"scope": "chat:write,incoming-webhook"},
    },
}


def client_for(provider):
    id_setting, secret_setting = PROVIDERS[provider]["client"]
    return getattr(settings, id_setting), getattr(settings, secret_setting)


def configured(provider):
    return all(client_for(provider))


def redirect_uri(provider):
    return settings.INTEGRATION_REDIRECT_BASE + provider + "/"


def exchange(provider, code):
    """Swap an authorization code for stored credentials and any options the
    provider hands back. Provider bodies never leak into exceptions."""
    if not code or len(code) > 2000:
        raise ProviderError("missing_code")
    client_id, client_secret = client_for(provider)
    if provider in {"google_calendar", "google_sheets", "gmail"}:
        body = request(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri(provider),
                "grant_type": "authorization_code",
            },
        )
        credentials = {
            "access_token": body["access_token"],
            "expires_at": (
                timezone.now() + timedelta(seconds=int(body.get("expires_in", 3600)))
            ).isoformat(),
        }
        if body.get("refresh_token"):
            credentials["refresh_token"] = body["refresh_token"]
        if provider == "gmail":
            profile = request(
                "GET",
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {body['access_token']}"},
            )
            if not profile.get("email") or profile.get("email_verified") is not True:
                raise ProviderError("gmail_sender_unverified")
            return credentials, {"sender_email": str(profile["email"])}
        return credentials, {}
    body = request(
        "POST",
        "https://slack.com/api/oauth.v2.access",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri(provider),
        },
    )
    if not body.get("ok") or not body.get("access_token"):
        raise ProviderError("slack_rejected")
    hook = body.get("incoming_webhook") or {}
    options = {
        key: str(value)[:200]
        for key, value in {
            "channel_id": hook.get("channel_id"),
            "channel_name": hook.get("channel"),
        }.items()
        if value
    }
    return {
        "access_token": body["access_token"],
        "team_id": str((body.get("team") or {}).get("id", ""))[:50],
    }, options


def revoke(config):
    """Best-effort remote revocation on disconnect. Local removal never depends on it."""
    credentials = json.loads(config.credentials)
    token = credentials.get("refresh_token") or credentials.get("access_token")
    if not token or config.is_test:
        return
    try:
        if config.provider in {"google_calendar", "google_sheets", "gmail"}:
            request("POST", "https://oauth2.googleapis.com/revoke", params={"token": token})
        elif config.provider == "slack":
            request(
                "POST",
                "https://slack.com/api/auth.revoke",
                headers={"Authorization": f"Bearer {token}"},
            )
    except ProviderError:
        pass


class IntegrationOAuthStartView(APIView):
    def post(self, request, workspace_id, provider):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        if provider not in PROVIDERS:
            return Response({"detail": "This integration has no hosted sign-in."}, status=404)
        from apps.billing.gating import check_feature

        check_feature(workspace_id, "integrations_unlocked")
        live = configured(provider)
        if not live and settings.CHANNEL_ADAPTER_MODE != "fake":
            service = "Google" if provider.startswith("google_") or provider == "gmail" else "Slack"
            return Response(
                {
                    "detail": f"{service} sign-in has not been configured by the platform administrator. "
                    f"Ask them to configure the {service} OAuth app before connecting. "
                    "An AI provider API key does not enable this connection.",
                    "code": "integration_oauth_not_configured",
                },
                status=409,
            )
        options = request.data.get("options", {})
        allowed = {
            "google_calendar": {"calendar_id"},
            "google_sheets": {"spreadsheet_id", "range"},
            "gmail": {"sender_email"},
            "slack": {"channel_id"},
        }[provider]
        if not isinstance(options, dict) or any(
            key not in allowed or not isinstance(value, str) or len(value) > 500
            for key, value in options.items()
        ):
            return Response({"detail": "Invalid integration destination options."}, status=400)
        if (
            provider == "google_sheets"
            and options
            and not options.get("spreadsheet_id", "").strip()
        ):
            return Response({"detail": "Enter the spreadsheet ID before connecting."}, status=400)
        if options:
            config, _ = IntegrationConfig.objects.for_workspace(workspace_id).get_or_create(
                workspace=member.workspace,
                provider=provider,
                defaults={"enabled": False, "status": "oauth_pending"},
            )
            config.options = {**config.options, **options}
            config.save(update_fields=["options"])
        state = secrets.token_urlsafe(32)
        OAuthState.objects.for_workspace(member.workspace).create(
            workspace=member.workspace,
            user=request.user,
            provider=provider,
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        if live:
            spec = PROVIDERS[provider]
            return Response(
                {
                    "authorization_url": spec["authorize"]
                    + "?"
                    + urlencode(
                        {
                            "client_id": client_for(provider)[0],
                            "redirect_uri": redirect_uri(provider),
                            "response_type": "code",
                            "state": state,
                            **spec["params"],
                        }
                    ),
                    "mode": "live",
                }
            )
        return Response(
            {
                "authorization_url": f"/api/integrations/callback/{provider}/?"
                + urlencode({"state": state, "code": LOCAL_CODE}),
                "mode": "fake",
            }
        )


class IntegrationOAuthCallbackView(APIView):
    def get(self, request, provider):
        state = request.query_params.get("state", "")
        if provider not in PROVIDERS or not state or len(state) > 200:
            return Response({"detail": "Invalid OAuth state."}, status=400)
        with transaction.atomic():
            pending = (
                OAuthState.all_objects.select_for_update()
                .filter(
                    state_hash=hashlib.sha256(state.encode()).hexdigest(),
                    provider=provider,
                    user=request.user,
                    consumed_at__isnull=True,
                    expires_at__gt=timezone.now(),
                )
                .first()
            )
            if pending is None:
                return Response({"detail": "OAuth state expired or already used."}, status=400)
            member = workspace_membership(request, pending.workspace_id, ["owner", "admin"])
            pending.consumed_at = timezone.now()
            pending.save(update_fields=["consumed_at"])
        target = f"/w/{pending.workspace_id}/integrations?provider={provider}&integration="
        if request.query_params.get("error"):
            return HttpResponseRedirect(target + "cancelled")
        code = request.query_params.get("code", "")
        is_test = not configured(provider)
        try:
            if is_test:
                if settings.CHANNEL_ADAPTER_MODE != "fake" or code != LOCAL_CODE:
                    raise ProviderError("test_integration_disabled")
                credentials, options = {}, {}
            else:
                credentials, options = exchange(provider, code)
            with transaction.atomic():
                config = (
                    IntegrationConfig.objects.for_workspace(pending.workspace_id)
                    .select_for_update()
                    .filter(provider=provider)
                    .first()
                )
                if config is None:
                    config = IntegrationConfig(workspace=member.workspace, provider=provider)
                previous = json.loads(config.credentials or "{}")
                # Google only returns a refresh token on first consent; keep the one we hold.
                if provider in {"google_calendar", "google_sheets", "gmail"} and not is_test:
                    credentials.setdefault("refresh_token", previous.get("refresh_token", ""))
                config.credentials = json.dumps(credentials)
                config.options = {**config.options, **options}
                config.enabled = True
                config.is_test = is_test
                config.status = "active"
                config.save()
                audit(
                    member.workspace,
                    request.user,
                    "integration.test_connected" if is_test else "integration.connected",
                    config.id,
                    provider=provider,
                )
        except (ProviderError, KeyError, ValueError, TypeError):
            return HttpResponseRedirect(target + "failed")
        return HttpResponseRedirect(target + ("test-connected" if is_test else "connected"))
