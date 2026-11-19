import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gating import PlanLimitExceeded, check_within_limit
from apps.platform_ops.tasks import classify_connection
from apps.tenants.models import Workspace
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .adapters import IntegrationUnavailable, exchange_oauth_code
from .models import ChannelConnection, OAuthState
from .transport import ProviderError


class ConnectionSerializer(serializers.ModelSerializer):
    # Soft-locked after a downgrade: still live, read-only for configuration.
    locked = serializers.SerializerMethodField()

    # Public profile facts for the account switcher; never the raw profile blob.
    followers = serializers.SerializerMethodField()

    def get_locked(self, obj):
        return obj.pk in self.context.get("locked", set())

    def get_followers(self, obj):
        value = (obj.profile or {}).get("followers_count")
        return value if isinstance(value, int) and value >= 0 else None

    class Meta:
        model = ChannelConnection
        fields = [
            "id",
            "provider",
            "display_name",
            "expires_at",
            "is_test",
            "status",
            "locked",
            "followers",
            "last_refreshed_at",
        ]


class ConnectionRefreshView(APIView):
    """Queue an immediate token refresh for every active Instagram connection. Other
    Meta channels use long-lived Page or system-user tokens with no refresh grant."""

    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        from apps.tenants.dispatch import enqueue_once

        from .tasks import refresh_connection

        connections = ChannelConnection.objects.for_workspace(member.workspace).filter(
            provider="instagram", status="active"
        )
        ids = list(connections.values_list("pk", flat=True))
        connections.update(refresh_due_at=timezone.now())
        for pk in ids:
            enqueue_once(refresh_connection, member.workspace_id, pk, ttl=300)
        audit(member.workspace, request.user, "channel.refresh_requested", member.workspace_id)
        return Response({"queued": len(ids)}, status=202)


class ConnectionListView(generics.ListAPIView):
    serializer_class = ConnectionSerializer

    def get_serializer_context(self):
        from apps.billing.gating import locked_connection_ids

        return {
            **super().get_serializer_context(),
            "locked": locked_connection_ids(self.kwargs["workspace_id"]),
        }

    def get_queryset(self):
        from apps.tenants.access import connection_ids

        member = workspace_membership(self.request, self.kwargs["workspace_id"])
        query = ChannelConnection.objects.for_workspace(member.workspace).defer("access_token")
        allowed = connection_ids(member)
        # Members limited to certain accounts see only those.
        if allowed is not None:
            query = query.filter(pk__in=allowed)
        return query


class MetaOAuthStartView(APIView):
    def post(self, request, workspace_id):
        member = workspace_membership(
            request,
            workspace_id,
            ["owner", "admin"],
            allow_pending=request.data.get("onboarding") is True,
        )
        # Gate before the OAuth dance, not after it.
        check_within_limit(workspace_id, "max_instagram_accounts")
        if settings.CHANNEL_ADAPTER_MODE == "disabled" or (
            settings.CHANNEL_ADAPTER_MODE == "live"
            and not (settings.META_APP_ID and settings.META_APP_SECRET)
        ):
            return Response(
                {"detail": "Configure the Meta app credentials and live channel mode first."},
                status=409,
            )
        state = secrets.token_urlsafe(32)
        if request.data.get("onboarding") is True:
            returns = request.session.get("instagram_onboarding", {})
            returns = dict(list(returns.items())[-4:])
            returns[hashlib.sha256(state.encode()).hexdigest()] = {
                "plan": str(request.data.get("plan", ""))[:40],
                "interval": "annual" if request.data.get("interval") == "annual" else "monthly",
            }
            request.session["instagram_onboarding"] = returns
        OAuthState.objects.for_workspace(member.workspace).create(
            workspace=member.workspace,
            user=request.user,
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        if settings.CHANNEL_ADAPTER_MODE == "live":
            if settings.INSTAGRAM_UNIFIED_LOGIN_CONFIG_ID:
                params = {
                    "client_id": settings.META_APP_ID,
                    "config_id": settings.INSTAGRAM_UNIFIED_LOGIN_CONFIG_ID,
                    "display": "popup",
                    "override_default_response_type": "true",
                    "redirect_uri": settings.META_REDIRECT_URI,
                    "response_type": "code",
                    "state": state,
                    "prompt": "login",
                }
                return Response(
                    {
                        "authorization_url": "https://www.facebook.com/dialog/oauth?"
                        + urlencode(params),
                        "mode": "live",
                    }
                )
            return Response(
                {
                    "authorization_url": "https://www.instagram.com/oauth/authorize?"
                    + urlencode(
                        {
                            "client_id": settings.META_APP_ID,
                            "redirect_uri": settings.META_REDIRECT_URI,
                            "scope": settings.META_SCOPES,
                            "response_type": "code",
                            "state": state,
                            "enable_fb_login": "0",
                            "force_authentication": "1",
                        }
                    ),
                    "mode": "live",
                }
            )
        return Response(
            {
                "authorization_url": "/api/meta/callback/?"
                + urlencode({"state": state, "code": "local-test-code"}),
                "mode": "fake",
            }
        )


class MetaOAuthCallbackView(APIView):
    def get(self, request):
        state = request.query_params.get("state", "")
        if not state or len(state) > 200:
            return Response({"detail": "Invalid OAuth state."}, status=400)
        returns = request.session.get("instagram_onboarding", {})
        with transaction.atomic():
            # State lookup is global only to locate its tenant, then membership is rechecked.
            pending = (
                OAuthState.all_objects.select_for_update()
                .filter(
                    state_hash=hashlib.sha256(state.encode()).hexdigest(),
                    user=request.user,
                    consumed_at__isnull=True,
                    expires_at__gt=timezone.now(),
                )
                .first()
            )
            if pending is None:
                return Response({"detail": "OAuth state expired or already used."}, status=400)
            member = workspace_membership(
                request,
                pending.workspace_id,
                ["owner", "admin"],
                allow_pending=pending.state_hash in returns,
            )
            pending.consumed_at = timezone.now()
            pending.save(update_fields=["consumed_at"])
        onboarding = returns.pop(pending.state_hash, None)
        request.session["instagram_onboarding"] = returns

        def destination(status):
            if onboarding is not None:
                return "/onboarding/?" + urlencode(
                    {**onboarding, "connection": status, "workspace": pending.workspace_id}
                )
            return f"/w/{pending.workspace_id}/integrations/?connection={status}"

        if request.query_params.get("error"):
            return HttpResponseRedirect(destination("cancelled"))
        try:
            credentials = exchange_oauth_code(
                request.query_params.get("code"), pending.workspace_id
            )
            with transaction.atomic():
                Workspace.objects.select_for_update().get(pk=pending.workspace_id)
                already = (
                    ChannelConnection.objects.for_workspace(pending.workspace_id)
                    .filter(provider="instagram", external_account_id=credentials.account_id)
                    .exclude(status="disconnected")
                    .exists()
                )
                if not already:
                    try:
                        check_within_limit(pending.workspace_id, "max_instagram_accounts")
                    except PlanLimitExceeded:
                        return HttpResponseRedirect(destination("limit"))
                connection, _ = ChannelConnection.objects.for_workspace(
                    pending.workspace_id
                ).update_or_create(
                    workspace_id=pending.workspace_id,
                    provider="instagram",
                    external_account_id=credentials.account_id,
                    defaults={
                        "display_name": credentials.display_name,
                        "access_token": credentials.access_token,
                        "expires_at": credentials.expires_at,
                        "is_test": settings.CHANNEL_ADAPTER_MODE == "fake",
                        "status": "active",
                        "profile": credentials.profile,
                        "meta_authorizer_id": credentials.meta_authorizer_id,
                        "refresh_due_at": (
                            None
                            if credentials.profile.get("unified_login")
                            else credentials.expires_at - timedelta(days=7)
                        ),
                    },
                )
                # A bio changes, so the marketing segment derived from it is re-run on
                # every reconnect, not only on first connect. Segmentation is reporting:
                # a broker hiccup must never cost someone their connection.
                try:
                    classify_connection.delay(str(connection.pk))
                except Exception:  # noqa: BLE001
                    logging.getLogger(__name__).warning("segment classification not queued")
                audit(
                    pending.workspace,
                    request.user,
                    "channel.test_connected" if connection.is_test else "channel.connected",
                    connection.id,
                    provider="instagram",
                )
        except (IntegrationUnavailable, IntegrityError, ProviderError, KeyError, ValueError):
            return Response(
                {"detail": "Connection failed. Start a new connection attempt."}, status=400
            )
        if onboarding is not None:
            from apps.platform_ops.growth import record_funnel_event

            record_funnel_event(
                flow="wizard",
                step="connect-instagram",
                status="completed",
                user=request.user,
                workspace=pending.workspace,
                is_owner=member.role == "owner",
            )
        return HttpResponseRedirect(
            destination("test-connected" if connection.is_test else "connected")
        )


class LinkedInOAuthStartView(APIView):
    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        check_within_limit(workspace_id, "max_instagram_accounts")
        if settings.CHANNEL_ADAPTER_MODE == "disabled" or (
            settings.CHANNEL_ADAPTER_MODE == "live"
            and not (settings.LINKEDIN_CLIENT_ID and settings.LINKEDIN_CLIENT_SECRET)
        ):
            return Response(
                {"detail": "Configure LinkedIn credentials and live channel mode first."},
                status=409,
            )
        if settings.CHANNEL_ADAPTER_MODE == "live" and not settings.LINKEDIN_MESSAGING_APPROVED:
            # Refuse the connection rather than take it and fail every send afterwards.
            return Response(
                {
                    "detail": "LinkedIn messaging is not available yet. It needs granted "
                    "messaging access on the LinkedIn app, confirmed against a real account."
                },
                status=409,
            )
        state = secrets.token_urlsafe(32)
        OAuthState.objects.for_workspace(member.workspace).create(
            workspace=member.workspace,
            user=request.user,
            provider="linkedin",
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        if settings.CHANNEL_ADAPTER_MODE == "live":
            return Response(
                {
                    "authorization_url": "https://www.linkedin.com/oauth/v2/authorization?"
                    + urlencode(
                        {
                            "response_type": "code",
                            "client_id": settings.LINKEDIN_CLIENT_ID,
                            "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
                            "state": state,
                            "scope": settings.LINKEDIN_SCOPES,
                        }
                    ),
                    "mode": "live",
                }
            )
        return Response(
            {
                "authorization_url": "/api/linkedin/callback/?"
                + urlencode({"state": state, "code": "local-test-linkedin-code"}),
                "mode": "fake",
            }
        )


class LinkedInOAuthCallbackView(APIView):
    def get(self, request):
        state = request.query_params.get("state", "")
        if not state or len(state) > 200:
            return Response({"detail": "Invalid OAuth state."}, status=400)
        with transaction.atomic():
            pending = (
                OAuthState.all_objects.select_for_update()
                .filter(
                    state_hash=hashlib.sha256(state.encode()).hexdigest(),
                    user=request.user,
                    provider="linkedin",
                    consumed_at__isnull=True,
                    expires_at__gt=timezone.now(),
                )
                .first()
            )
            if pending is None:
                return Response({"detail": "OAuth state expired or already used."}, status=400)
            workspace_membership(request, pending.workspace_id, ["owner", "admin"])
            pending.consumed_at = timezone.now()
            pending.save(update_fields=["consumed_at"])
        if request.query_params.get("error"):
            return HttpResponseRedirect("/?connection=cancelled")
        try:
            account_id = "urn:li:organization:123456"
            display_name = "LinkedIn Company Page"
            access_token = "fake-linkedin-token"
            if settings.CHANNEL_ADAPTER_MODE == "live":
                import httpx

                code = request.query_params.get("code")
                token_res = httpx.post(
                    "https://www.linkedin.com/oauth/v2/accessToken",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
                        "client_id": settings.LINKEDIN_CLIENT_ID,
                        "client_secret": settings.LINKEDIN_CLIENT_SECRET,
                    },
                    timeout=15,
                )
                if token_res.is_success:
                    token_data = token_res.json()
                    access_token = token_data.get("access_token", "")
                    userinfo_res = httpx.get(
                        "https://api.linkedin.com/v2/userinfo",
                        headers={"Authorization": f"Bearer {access_token}"},
                        timeout=15,
                    )
                    if userinfo_res.is_success:
                        user_info = userinfo_res.json()
                        account_id = f"urn:li:person:{user_info.get('sub', 'unknown')}"
                        display_name = user_info.get("name", "LinkedIn Profile")
            with transaction.atomic():
                Workspace.objects.select_for_update().get(pk=pending.workspace_id)
                connection, _ = ChannelConnection.objects.for_workspace(
                    pending.workspace_id
                ).update_or_create(
                    workspace_id=pending.workspace_id,
                    provider="linkedin",
                    external_account_id=account_id,
                    defaults={
                        "display_name": display_name,
                        "access_token": access_token,
                        "expires_at": timezone.now() + timedelta(days=60),
                        "is_test": settings.CHANNEL_ADAPTER_MODE == "fake",
                        "status": "active",
                        "profile": {"platform": "linkedin"},
                        "refresh_due_at": timezone.now() + timedelta(days=50),
                    },
                )
                audit(
                    pending.workspace,
                    request.user,
                    "channel.test_connected" if connection.is_test else "channel.connected",
                    connection.id,
                    provider="linkedin",
                )
        except Exception:
            return Response(
                {"detail": "Connection failed. Start a new connection attempt."}, status=400
            )
        return HttpResponseRedirect(
            f"/w/{pending.workspace_id}/integrations/?connection={'test-connected' if connection.is_test else 'connected'}"
        )
