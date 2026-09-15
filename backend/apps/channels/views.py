import hashlib
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

from apps.tenants.models import Workspace
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .adapters import IntegrationUnavailable, exchange_oauth_code
from .models import ChannelConnection, OAuthState
from .transport import ProviderError


class ConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChannelConnection
        fields = ["id", "provider", "display_name", "expires_at", "is_test", "status"]


class ConnectionListView(generics.ListAPIView):
    serializer_class = ConnectionSerializer

    def get_queryset(self):
        member = workspace_membership(self.request, self.kwargs["workspace_id"])
        return ChannelConnection.objects.for_workspace(member.workspace).defer("access_token")


class MetaOAuthStartView(APIView):
    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        if settings.CHANNEL_ADAPTER_MODE == "disabled" or (
            settings.CHANNEL_ADAPTER_MODE == "live"
            and not (settings.META_APP_ID and settings.META_APP_SECRET)
        ):
            return Response(
                {"detail": "Configure the Meta app credentials and live channel mode first."},
                status=503,
            )
        state = secrets.token_urlsafe(32)
        OAuthState.objects.for_workspace(member.workspace).create(
            workspace=member.workspace,
            user=request.user,
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        if settings.CHANNEL_ADAPTER_MODE == "live":
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
            workspace_membership(request, pending.workspace_id, ["owner", "admin"])
            pending.consumed_at = timezone.now()
            pending.save(update_fields=["consumed_at"])
        if request.query_params.get("error"):
            return HttpResponseRedirect("/?connection=cancelled")
        try:
            credentials = exchange_oauth_code(
                request.query_params.get("code"), pending.workspace_id
            )
            with transaction.atomic():
                from apps.billing.services import account_for

                Workspace.objects.select_for_update().get(pk=pending.workspace_id)
                already = (
                    ChannelConnection.objects.for_workspace(pending.workspace_id)
                    .filter(provider="instagram", external_account_id=credentials.account_id)
                    .exclude(status="disconnected")
                    .exists()
                )
                active = (
                    ChannelConnection.objects.for_workspace(pending.workspace_id)
                    .exclude(status="disconnected")
                    .count()
                )
                if not already and active >= account_for(pending.workspace_id).channel_limit:
                    return HttpResponseRedirect("/?connection=limit")
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
                        "refresh_due_at": credentials.expires_at - timedelta(days=7),
                    },
                )
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
        return HttpResponseRedirect(
            "/?connection=" + ("test-connected" if connection.is_test else "connected")
        )
