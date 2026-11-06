"""WhatsApp Cloud API onboarding. Client-supplied asset IDs are never trusted."""

import hashlib
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gating import check_connection_unlocked, check_within_limit
from apps.platform_ops.security import assert_enabled
from apps.tenants.models import Workspace
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import ChannelConnection, OAuthState
from .transport import ProviderError, request


def graph(method, path, token, **kwargs):
    return request(
        method,
        f"https://graph.facebook.com/{settings.META_API_VERSION}/{path}",
        headers={"Authorization": f"Bearer {token}"} if token else {},
        **kwargs,
    )


def setup_info():
    missing = []
    for present, label in [
        (settings.CHANNEL_ADAPTER_MODE == "live", "Enable live messaging"),
        (settings.META_APP_ID and settings.META_APP_SECRET, "Add the Meta app credentials"),
        (settings.WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID, "Add the WhatsApp signup configuration"),
        (
            settings.WHATSAPP_APP_SECRET and settings.META_WEBHOOK_VERIFY_TOKEN,
            "Configure signed WhatsApp notifications",
        ),
        (urlsplit(settings.PUBLIC_APP_URL).scheme == "https", "Set a public HTTPS app address"),
    ]:
        if not present:
            missing.append(label)
    return {
        "ready": not missing,
        "steps": missing,
        "webhook_url": settings.PUBLIC_APP_URL.rstrip("/") + "/webhooks/whatsapp/",
    }


class WhatsAppConnectView(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        return Response(setup_info())

    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        assert_enabled(workspace_id, "integration:whatsapp")
        reconnect = None
        if request.data.get("connection_id"):
            try:
                reconnect_id = uuid.UUID(str(request.data["connection_id"]))
            except ValueError:
                raise serializers.ValidationError(
                    "Choose the WhatsApp connection to reconnect."
                ) from None
            reconnect = get_object_or_404(
                ChannelConnection.objects.for_workspace(workspace_id),
                pk=reconnect_id,
                provider="whatsapp",
                is_test=False,
            )
        if reconnect and reconnect.status != "disconnected":
            check_connection_unlocked(reconnect)
        else:
            check_within_limit(workspace_id, "max_instagram_accounts")
        info = setup_info()
        if not info["ready"]:
            return Response(
                {**info, "detail": "WhatsApp needs a little setup by your administrator."},
                status=409,
            )
        state = secrets.token_urlsafe(32)
        OAuthState.objects.for_workspace(workspace_id).create(
            workspace=member.workspace,
            user=request.user,
            provider="whatsapp",
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        return Response(
            {
                "state": state,
                "app_id": settings.META_APP_ID,
                "config_id": settings.WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID,
                "version": settings.META_API_VERSION,
            }
        )


class CompleteSerializer(serializers.Serializer):
    state = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=4000, write_only=True)
    waba_id = serializers.RegexField(r"^[0-9]{1,40}$")
    phone_number_id = serializers.RegexField(r"^[0-9]{1,40}$")


def verified_phone(waba_id, phone_id, token):
    # Traverse only Meta's fixed graph endpoint; never follow provider paging URLs.
    after = None
    for _ in range(20):
        params = {"fields": "id,display_phone_number,verified_name", "limit": 100}
        if after:
            params["after"] = after
        body = graph("GET", f"{waba_id}/phone_numbers", token, params=params)
        for phone in body.get("data", []):
            if str(phone.get("id")) == phone_id:
                return phone
        paging = body.get("paging", {})
        after = paging.get("cursors", {}).get("after") if paging.get("next") else None
        if not after:
            break
    raise serializers.ValidationError(
        "Choose a phone number belonging to the business you connected."
    )


class WhatsAppCompleteView(APIView):
    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        assert_enabled(workspace_id, "integration:whatsapp")
        if not setup_info()["ready"]:
            raise serializers.ValidationError(
                "Ask your administrator to finish the WhatsApp setup."
            )
        serializer = CompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            state = (
                OAuthState.objects.for_workspace(workspace_id)
                .select_for_update()
                .filter(
                    provider="whatsapp",
                    user=request.user,
                    state_hash=hashlib.sha256(data["state"].encode()).hexdigest(),
                    consumed_at__isnull=True,
                    expires_at__gt=timezone.now(),
                )
                .first()
            )
            if not state:
                raise serializers.ValidationError("This connection attempt expired. Start again.")
            state.consumed_at = timezone.now()
            state.save(update_fields=["consumed_at"])
        try:
            grant = graph(
                "GET",
                "oauth/access_token",
                "",
                params={
                    "client_id": settings.META_APP_ID,
                    "client_secret": settings.META_APP_SECRET,
                    "code": data["code"],
                },
            )
            token = grant.get("access_token")
            if not isinstance(token, str) or not token:
                raise ProviderError()
            debug = graph(
                "GET",
                "debug_token",
                f"{settings.META_APP_ID}|{settings.META_APP_SECRET}",
                params={"input_token": token},
            ).get("data", {})
            scopes = set(debug.get("scopes", []))
            if (
                debug.get("is_valid") is not True
                or str(debug.get("app_id")) != settings.META_APP_ID
                or not {"whatsapp_business_management", "whatsapp_business_messaging"} <= scopes
            ):
                raise serializers.ValidationError(
                    "Allow WhatsApp account management and messaging, then reconnect."
                )
            allowed = {
                str(asset)
                for scope in debug.get("granular_scopes", [])
                if scope.get("scope") == "whatsapp_business_management"
                for asset in scope.get("target_ids", [])
            }
            if data["waba_id"] not in allowed:
                raise serializers.ValidationError(
                    "Choose the WhatsApp business you shared in the connection window."
                )
            phone = verified_phone(data["waba_id"], data["phone_number_id"], token)
            expiry = int(debug.get("expires_at") or 0)
            access_expiry = int(debug.get("data_access_expires_at") or 0)
            deadlines = [value for value in (expiry, access_expiry) if value > 0]
            expires_at = (
                timezone.datetime.fromtimestamp(min(deadlines), tz=timezone.get_current_timezone())
                if deadlines
                else timezone.now() + timedelta(days=3650)
            )
            if expires_at <= timezone.now():
                raise ProviderError()
            with transaction.atomic():
                Workspace.objects.select_for_update().get(pk=workspace_id)
                existing = (
                    ChannelConnection.all_objects.select_for_update()
                    .filter(provider="whatsapp", external_account_id=data["phone_number_id"])
                    .first()
                )
                if existing and existing.workspace_id != member.workspace_id:
                    raise serializers.ValidationError(
                        "This number is already connected to another workspace."
                    )
                if existing and existing.status != "disconnected":
                    check_connection_unlocked(existing)
                else:
                    check_within_limit(workspace_id, "max_instagram_accounts")
                item = existing or ChannelConnection(
                    workspace=member.workspace,
                    provider="whatsapp",
                    external_account_id=data["phone_number_id"],
                )
                item.access_token = token
                item.expires_at = expires_at
                item.is_test = False
                item.status = "setup_required"
                item.display_name = str(
                    phone.get("verified_name") or phone.get("display_phone_number") or "WhatsApp"
                )[:150]
                item.profile = {
                    "waba_id": data["waba_id"],
                    "display_phone_number": phone.get("display_phone_number", ""),
                }
                item.webhook_secret = secrets.token_urlsafe(32)
                item.save()
                audit(member.workspace, request.user, "whatsapp.authorized", item.pk)
        except (ProviderError, IntegrityError):
            raise serializers.ValidationError(
                "WhatsApp could not finish connecting. Please reconnect and try again."
            ) from None
        return Response(
            {"id": item.pk, "status": item.status, "display_name": item.display_name}, status=202
        )


class ActivateSerializer(serializers.Serializer):
    pin = serializers.RegexField(
        r"^[0-9]{6}$",
        required=False,
        write_only=True,
        error_messages={"invalid": "Enter your six-digit WhatsApp security PIN."},
    )
    already_registered = serializers.BooleanField(default=False)


class WhatsAppActivateView(APIView):
    def post(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        assert_enabled(workspace_id, "integration:whatsapp")
        serializer = ActivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            item = get_object_or_404(
                ChannelConnection.objects.for_workspace(workspace_id).select_for_update(),
                pk=pk,
                provider="whatsapp",
                is_test=False,
            )
            check_connection_unlocked(item)
            if item.status == "active":
                return Response({"status": "active"})
            if item.status != "setup_required" or item.expires_at <= timezone.now():
                raise serializers.ValidationError("Reconnect this number to continue.")
            if settings.CHANNEL_ADAPTER_MODE != "live":
                raise serializers.ValidationError(
                    "Live WhatsApp connections are currently unavailable."
                )
            waba = item.profile.get("waba_id", "")
            try:
                verified_phone(waba, item.external_account_id, item.access_token)
                if not item.profile.get("registered"):
                    if data["already_registered"]:
                        phone = graph(
                            "GET",
                            item.external_account_id,
                            item.access_token,
                            params={"fields": "id,status"},
                        )
                        if phone.get("status") != "CONNECTED":
                            raise serializers.ValidationError(
                                "This number needs registration. Enter its security PIN to continue."
                            )
                    else:
                        if not data.get("pin"):
                            raise serializers.ValidationError(
                                {"pin": "Enter your six-digit WhatsApp security PIN."}
                            )
                        result = graph(
                            "POST",
                            f"{item.external_account_id}/register",
                            item.access_token,
                            json={"messaging_product": "whatsapp", "pin": data["pin"]},
                        )
                        if result.get("success") not in (True, "true"):
                            raise ProviderError()
                    # Persist the checkpoint before subscribing: a retry never resets the PIN.
                    item.profile = {**item.profile, "registered": True}
                    item.save(update_fields=["profile"])
                result = graph("POST", f"{waba}/subscribed_apps", item.access_token, json={})
                if result.get("success") not in (True, "true"):
                    raise ProviderError()
            except ProviderError:
                # Keep the registered checkpoint even if Meta rejects the subscription.
                return Response(
                    {
                        "detail": "WhatsApp could not finish setup. Check the number and permissions, then try again."
                    },
                    status=400,
                )
            item.status = "active"
            item.save(update_fields=["status"])
            audit(member.workspace, request.user, "whatsapp.connected", item.pk)
        return Response({"id": item.pk, "status": "active"})
