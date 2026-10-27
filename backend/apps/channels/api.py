import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gating import check_within_limit
from apps.tenants.models import Workspace
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .adapters import PROVIDERS, IntegrationUnavailable, adapter_for
from .models import ChannelConnection, Delivery, WebhookEvent
from .transport import ProviderError


class AccountPostsView(APIView):
    def get(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        connection = get_object_or_404(
            ChannelConnection.objects.for_workspace(workspace_id),
            pk=pk,
            provider__in=["instagram", "messenger"],
            status="active",
            expires_at__gt=timezone.now(),
        )
        from apps.billing.gating import check_connection_unlocked

        check_connection_unlocked(connection)
        try:
            return Response({"results": adapter_for(connection).recent_posts()})
        except (IntegrationUnavailable, ProviderError):
            raise serializers.ValidationError(
                "Posts could not be loaded. Check this account's connection and permissions."
            ) from None


class ConnectSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=PROVIDERS)
    external_account_id = serializers.RegexField(r"^[A-Za-z0-9_-]{1,200}$")
    display_name = serializers.CharField(max_length=150)
    access_token = serializers.CharField(
        write_only=True, max_length=4000, required=False, allow_blank=True
    )
    expires_at = serializers.DateTimeField(required=False)
    is_test = serializers.BooleanField(default=False)
    business_account_id = serializers.RegexField(r"^[0-9]{1,40}$", required=False, allow_blank=True)


class ConnectView(APIView):
    @transaction.atomic
    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        serializer = ConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        business_account_id = data.pop("business_account_id", "")
        if business_account_id and data["provider"] != "whatsapp":
            raise serializers.ValidationError(
                {"business_account_id": "This value is only needed for WhatsApp."}
            )
        if data["is_test"] and settings.CHANNEL_ADAPTER_MODE != "fake":
            raise serializers.ValidationError("Test connections are disabled.")
        if not data["is_test"] and (
            settings.CHANNEL_ADAPTER_MODE != "live" or not data.get("access_token")
        ):
            raise serializers.ValidationError("Enable live mode and provide a provider token.")
        if not data["is_test"] and data["provider"] == "instagram":
            raise serializers.ValidationError("Connect Instagram using its OAuth flow.")
        Workspace.objects.select_for_update().get(pk=workspace_id)
        existing = (
            ChannelConnection.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(provider="whatsapp", external_account_id=data["external_account_id"])
            .first()
            if data["provider"] == "whatsapp"
            else None
        )
        if existing and existing.status != "disconnected":
            from apps.billing.gating import check_connection_unlocked

            check_connection_unlocked(existing)
        else:
            check_within_limit(workspace_id, "max_instagram_accounts")
        try:
            with transaction.atomic():
                defaults = dict(
                    **data,
                    **({"access_token": "local-test-token"} if "access_token" not in data else {}),
                    **(
                        {"expires_at": timezone.now() + timedelta(days=365)}
                        if "expires_at" not in data
                        else {}
                    ),
                    webhook_secret=secrets.token_urlsafe(32),
                    status="active" if data["is_test"] else "verifying",
                )
                if business_account_id:
                    defaults["profile"] = {"waba_id": business_account_id}
                if existing:
                    item = existing
                    for field, value in defaults.items():
                        setattr(item, field, value)
                    item.save()
                else:
                    item = ChannelConnection.objects.for_workspace(workspace_id).create(
                        workspace=member.workspace,
                        **defaults,
                    )
        except IntegrityError:
            raise serializers.ValidationError("This account is already connected.") from None
        audit(member.workspace, request.user, "channel.connection_requested", item.id)
        return Response({"id": item.id, "status": item.status}, status=202)


class SimulateView(APIView):
    def post(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        connection = get_object_or_404(
            ChannelConnection.objects.for_workspace(workspace_id),
            pk=pk,
            is_test=True,
            status="active",
        )
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise serializers.ValidationError("Local simulation is disabled.")
        from apps.billing.gating import check_connection_unlocked

        check_connection_unlocked(connection)
        text = request.data.get("text", "")
        if not isinstance(text, str) or not 1 <= len(text) <= 2000:
            raise serializers.ValidationError("Provide 1–2000 characters.")
        kind = request.data.get("kind", "dm")
        if kind not in {"dm", "comment", "story_reply", "live_comment"}:
            raise serializers.ValidationError("Invalid event kind.")
        sender = str(request.data.get("sender_id", "test-lead"))[:100]
        payload = {"text": text, "sender_id": sender, "kind": kind}
        if kind in {"comment", "live_comment"}:
            payload["comment_id"] = "test-comment-" + secrets.token_hex(8)
            post_id = request.data.get("post_id", "")
            if post_id:
                from .commenting import POST_ID

                if not isinstance(post_id, str) or not POST_ID.fullmatch(post_id):
                    raise serializers.ValidationError("Provide a valid post ID.")
                payload["post_id"] = post_id
        item = WebhookEvent.objects.for_workspace(workspace_id).create(
            workspace_id=workspace_id,
            connection=connection,
            event_id="test-" + secrets.token_hex(16),
            payload=json.dumps(payload),
            available_at=timezone.now(),
        )
        return Response({"id": item.id, "status": item.status}, status=202)


class DeliveryList(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        return Response(
            list(
                Delivery.objects.for_workspace(workspace_id)
                .order_by("-created_at")
                .values("id", "recipient_id", "status", "attempts", "error_code", "created_at")[
                    :100
                ]
            )
        )


class DisconnectView(APIView):
    def post(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        connection = get_object_or_404(ChannelConnection.objects.for_workspace(workspace_id), pk=pk)
        connection.status = "disconnected"
        connection.access_token = ""
        connection.webhook_secret = ""
        connection.save()
        audit(member.workspace, request.user, "channel.disconnected", connection.id)
        return Response({"status": "disconnected"})
