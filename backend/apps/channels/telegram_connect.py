import secrets
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gating import check_connection_unlocked, check_within_limit
from apps.platform_ops.security import blocked
from apps.tenants.models import Workspace
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import ChannelConnection
from .providers import TelegramAdapter
from .transport import ProviderError


class TelegramTokenSerializer(serializers.Serializer):
    access_token = serializers.RegexField(
        r"^[0-9]+:[A-Za-z0-9_-]+$", max_length=4000, write_only=True
    )


class TelegramConnectView(APIView):
    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        if settings.CHANNEL_ADAPTER_MODE != "live":
            raise serializers.ValidationError(
                "Live Telegram connections are not enabled on this server."
            )
        origin = urlsplit(settings.PUBLIC_APP_URL)
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise serializers.ValidationError(
                "Telegram needs a public HTTPS address. Ask your administrator to configure PUBLIC_APP_URL, then try again. Your bot token has not been saved."
            )
        serializer = TelegramTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data["access_token"]
        if blocked(workspace_id, "integration:telegram"):
            raise serializers.ValidationError(
                "Telegram connections are paused by your administrator."
            )
        try:
            profile = TelegramAdapter(SimpleNamespace(access_token=token)).call("getMe", {})
        except ProviderError:
            raise serializers.ValidationError(
                {
                    "access_token": "The bot could not be verified. Check the token from BotFather and try again."
                }
            ) from None
        if (
            not isinstance(profile, dict)
            or profile.get("is_bot") is not True
            or type(profile.get("id")) is not int
        ):
            raise serializers.ValidationError(
                {"access_token": "This token did not identify a Telegram bot."}
            )
        bot_id = str(profile["id"])
        try:
            with transaction.atomic():
                Workspace.objects.select_for_update().get(pk=workspace_id)
                connection = (
                    ChannelConnection.all_objects.select_for_update()
                    .filter(provider="telegram", external_account_id=bot_id)
                    .first()
                )
                if connection and connection.workspace_id != member.workspace_id:
                    raise serializers.ValidationError(
                        "This bot is already linked to another workspace. Use a different bot or contact support to move the connection."
                    )
                if connection and connection.status != "disconnected":
                    check_connection_unlocked(connection)
                else:
                    check_within_limit(workspace_id, "max_instagram_accounts")
                if not connection:
                    connection = ChannelConnection(
                        workspace=member.workspace, provider="telegram", external_account_id=bot_id
                    )
                connection.display_name = str(
                    profile.get("first_name") or profile.get("username") or "Telegram bot"
                )[:150]
                connection.access_token = token
                connection.webhook_secret = connection.webhook_secret or secrets.token_urlsafe(32)
                connection.expires_at = timezone.now() + timedelta(days=365)
                connection.is_test = False
                connection.profile = {
                    **connection.profile,
                    "username": str(profile.get("username") or "")[:150],
                }
                connection.status = "verifying"
                connection.save()
                try:
                    registered = TelegramAdapter(connection).configure_webhook(
                        settings.PUBLIC_APP_URL + f"/webhooks/telegram/{connection.pk}/"
                    )
                    if registered is not True:
                        raise ProviderError("telegram_rejected")
                except ProviderError:
                    connection.status = "reconnect_required"
                else:
                    connection.status = "active"
                connection.save(update_fields=["status"])
                audit(
                    member.workspace,
                    request.user,
                    "channel.connected"
                    if connection.status == "active"
                    else "channel.connection_failed",
                    connection.pk,
                    provider="telegram",
                )
        except IntegrityError:
            raise serializers.ValidationError(
                "This bot is being connected elsewhere. Refresh your channels and try again."
            ) from None
        if connection.status != "active":
            return Response(
                {
                    "detail": "Your bot was verified, but its webhook could not be registered. Check the public HTTPS address and try connecting again."
                },
                status=400,
            )
        return Response(
            {
                "id": connection.pk,
                "status": "active",
                "display_name": connection.display_name,
                "username": connection.profile["username"],
            }
        )
