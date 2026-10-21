import json
import re
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.channels.models import ChannelConnection, WebhookEvent
from apps.crm.models import ChannelIdentity, Message
from apps.tenants.models import Workspace
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import DeepLink, ShieldEvent, ShieldRule, WebChatSettings

PLATFORMS = {"instagram", "whatsapp", "youtube", "telegram", "custom"}
ACTIONS = {"hide", "delete", "flag"}
CODE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
HOSTNAME = re.compile(r"^[a-z0-9.-]{1,253}$")


# Deep links


class DeepLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeepLink
        fields = ["id", "title", "platform", "target", "code", "clicks", "active", "created_at"]
        read_only_fields = ["id", "clicks", "created_at"]

    def validate_platform(self, value):
        if value not in PLATFORMS:
            raise serializers.ValidationError("Unknown platform.")
        return value

    def validate_target(self, value):
        if not value.startswith("https://"):
            raise serializers.ValidationError("The target must be an HTTPS link.")
        return value

    def validate_code(self, value):
        value = value.strip().lower()
        if not CODE.match(value):
            raise serializers.ValidationError(
                "Use 2–40 lowercase letters, digits or dashes for the link code."
            )
        return value


class DeepLinkList(generics.ListCreateAPIView):
    serializer_class = DeepLinkSerializer
    pagination_class = None

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"])
        return DeepLink.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_create(self, serializer):
        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        try:
            with transaction.atomic():
                item = serializer.save(workspace=member.workspace)
        except IntegrityError:
            raise serializers.ValidationError(
                {"code": "That link code is already taken."}
            ) from None
        audit(member.workspace, self.request.user, "deeplink.created", item.id)


class DeepLinkDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DeepLinkSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return DeepLink.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise serializers.ValidationError(
                {"code": "That link code is already taken."}
            ) from None


class DeepLinkRedirect(APIView):
    """Anonymous: count the click and send the visitor on. Paused links are not found."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def get(self, request, code):
        link = get_object_or_404(DeepLink.all_objects, code=code.lower(), active=True)
        DeepLink.all_objects.filter(pk=link.pk).update(clicks=F("clicks") + 1)
        return HttpResponseRedirect(link.target)


# Comment shield


class ShieldRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShieldRule
        fields = ["id", "name", "keywords", "action", "enabled", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_keywords(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Keywords must be a list.")
        cleaned = []
        for keyword in value:
            if not isinstance(keyword, str):
                raise serializers.ValidationError("Keywords must be text.")
            keyword = keyword.strip().lower()[:60]
            if keyword and keyword not in cleaned:
                cleaned.append(keyword)
        if not 1 <= len(cleaned) <= 50:
            raise serializers.ValidationError("Add 1–50 keywords.")
        return cleaned

    def validate_action(self, value):
        if value not in ACTIONS:
            raise serializers.ValidationError("Action must be hide, delete or flag.")
        return value


class ShieldRuleList(generics.ListCreateAPIView):
    serializer_class = ShieldRuleSerializer
    pagination_class = None

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"])
        return ShieldRule.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_create(self, serializer):
        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        item = serializer.save(workspace=member.workspace)
        audit(member.workspace, self.request.user, "shield.rule_created", item.id)


class ShieldRuleDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ShieldRuleSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return ShieldRule.objects.for_workspace(self.kwargs["workspace_id"])


class ShieldEventSerializer(serializers.ModelSerializer):
    provider = serializers.CharField(source="connection.provider", read_only=True)

    class Meta:
        model = ShieldEvent
        fields = [
            "id",
            "rule_name",
            "provider",
            "comment_id",
            "author",
            "text",
            "action_taken",
            "created_at",
        ]


class ShieldEventList(generics.ListAPIView):
    serializer_class = ShieldEventSerializer
    pagination_class = None

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"])
        return (
            ShieldEvent.objects.for_workspace(self.kwargs["workspace_id"])
            .select_related("connection")
            .order_by("-created_at", "-id")[:200]
        )


# Web chat


class WebChatSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebChatSettings
        fields = ["title", "greeting", "color", "bot_enabled", "allowed_domains", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate_color(self, value):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise serializers.ValidationError("Use a hex colour such as #347359.")
        return value.lower()

    def validate_allowed_domains(self, value):
        if not isinstance(value, list) or len(value) > 20:
            raise serializers.ValidationError("List up to 20 hostnames.")
        cleaned = []
        for host in value:
            host = str(host).strip().lower().removeprefix("https://").removeprefix("http://")
            host = host.split("/")[0]
            if host and not HOSTNAME.match(host):
                raise serializers.ValidationError(f"{host} is not a hostname.")
            if host and host not in cleaned:
                cleaned.append(host)
        return cleaned


def webchat_defaults(workspace):
    return WebChatSettings(workspace=workspace)


class WebChatSettingsView(APIView):
    def get(self, request, workspace_id):
        member = workspace_membership(request, workspace_id)
        item = WebChatSettings.objects.for_workspace(workspace_id).first()
        return Response(WebChatSettingsSerializer(item or webchat_defaults(member.workspace)).data)

    def put(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        item = WebChatSettings.objects.for_workspace(workspace_id).first()
        serializer = WebChatSettingsSerializer(item, data=request.data, partial=bool(item))
        serializer.is_valid(raise_exception=True)
        item = serializer.save(workspace=member.workspace)
        audit(member.workspace, request.user, "webchat.updated", item.id)
        return Response(WebChatSettingsSerializer(item).data)


def embedding_host(request):
    """Hostname of the page embedding the widget, from Origin or Referer."""
    source = request.headers.get("Origin") or request.headers.get("Referer") or ""
    return (urlsplit(source).hostname or "").lower()


def allowed_to_embed(settings, request):
    if not settings.allowed_domains:
        return True
    host = embedding_host(request)
    return any(
        host == allowed or host.endswith("." + allowed) for allowed in settings.allowed_domains
    )


def webchat_connection(workspace):
    """The workspace's single web chat channel, created on first use."""
    connection = (
        ChannelConnection.objects.for_workspace(workspace.pk).filter(provider="webchat").first()
    )
    if connection:
        return connection
    return ChannelConnection.objects.for_workspace(workspace.pk).create(
        workspace=workspace,
        provider="webchat",
        external_account_id=f"webchat-{workspace.pk}",
        display_name="Website chat",
        access_token="",
        expires_at=timezone.now() + timedelta(days=36500),
        status="active",
    )


class WebChatThrottle(AnonRateThrottle):
    rate = "60/min"


class PublicWebChatView(APIView):
    """What the embedded widget needs: its look, and a way to send and read messages."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [WebChatThrottle]

    def settings_for(self, request, workspace_id):
        workspace = get_object_or_404(Workspace, pk=workspace_id)
        item = WebChatSettings.objects.for_workspace(workspace.pk).first() or webchat_defaults(
            workspace
        )
        if not allowed_to_embed(item, request):
            raise serializers.ValidationError("This site may not embed the widget.")
        return workspace, item

    def get(self, request, workspace_id):
        workspace, item = self.settings_for(request, workspace_id)
        visitor = str(request.query_params.get("visitor", ""))[:100]
        messages = []
        if visitor:
            identity = (
                ChannelIdentity.objects.for_workspace(workspace.pk)
                .filter(connection__provider="webchat", external_id=visitor)
                .select_related("conversation")
                .first()
            )
            conversation = getattr(identity, "conversation", None) if identity else None
            if conversation:
                messages = [
                    {
                        "id": str(message.id),
                        "direction": message.direction,
                        "text": message.text,
                        "created_at": message.created_at.isoformat(),
                    }
                    for message in Message.objects.for_workspace(workspace.pk)
                    .filter(conversation=conversation)
                    .order_by("created_at", "id")[:200]
                ]
        return Response(
            {
                "title": item.title,
                "greeting": item.greeting,
                "color": item.color,
                "bot_enabled": item.bot_enabled,
                "messages": messages,
            }
        )

    def post(self, request, workspace_id):
        workspace, _ = self.settings_for(request, workspace_id)
        text = request.data.get("text", "")
        visitor = str(request.data.get("visitor", ""))[:100]
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise serializers.ValidationError("Write 1–2000 characters.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", visitor):
            raise serializers.ValidationError("Invalid visitor id.")
        from apps.crm.services import receive

        with transaction.atomic():
            connection = webchat_connection(workspace)
            event = WebhookEvent.objects.for_workspace(workspace.pk).create(
                workspace=workspace,
                connection=connection,
                event_id="webchat-" + secrets.token_hex(16),
                payload=json.dumps({"text": text.strip(), "sender_id": visitor, "kind": "dm"}),
                available_at=timezone.now(),
                status="processed",
                processed_at=timezone.now(),
            )
            message = receive(event, {"text": text.strip(), "sender_id": visitor, "kind": "dm"})
        return Response({"id": str(message.id)}, status=201)
