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

from .adapters import PROVIDERS
from .models import ChannelConnection, Delivery, WebhookEvent


class ConnectSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=PROVIDERS)
    external_account_id = serializers.RegexField(r"^[A-Za-z0-9_-]{1,200}$")
    display_name = serializers.CharField(max_length=150)
    access_token = serializers.CharField(
        write_only=True, max_length=4000, required=False, allow_blank=True
    )
    expires_at = serializers.DateTimeField(required=False)
    is_test = serializers.BooleanField(default=False)


class ConnectView(APIView):
    @transaction.atomic
    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        serializer = ConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["is_test"] and settings.CHANNEL_ADAPTER_MODE != "fake":
            raise serializers.ValidationError("Test connections are disabled.")
        if not data["is_test"] and (
            settings.CHANNEL_ADAPTER_MODE != "live" or not data.get("access_token")
        ):
            raise serializers.ValidationError("Enable live mode and provide a provider token.")
        if not data["is_test"] and data["provider"] == "instagram":
            raise serializers.ValidationError("Connect Instagram using its OAuth flow.")
        Workspace.objects.select_for_update().get(pk=workspace_id)
        check_within_limit(workspace_id, "max_instagram_accounts")
        try:
            with transaction.atomic():
                item = ChannelConnection.objects.for_workspace(workspace_id).create(
                    workspace=member.workspace,
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
