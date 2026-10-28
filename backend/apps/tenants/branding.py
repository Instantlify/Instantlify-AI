"""White-label: agencies own client workspaces and brand the app they see."""

import hashlib
import re

from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseNotModified
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import Membership, Workspace, WorkspaceBranding
from .permissions import workspace_membership
from .services import audit, create_workspace

DEFAULT_BRANDING = {
    "brand_name": "Nemio",
    "logo_url": "",
    "primary_color": "#10244a",
    "sidebar_bg_color": "#ffffff",
    "sidebar_text_color": "#41516e",
    "support_email": "",
    "hide_platform_branding": False,
}


def logo_url(branding):
    if branding.logo_digest:
        return f"/api/public/workspace-logos/{branding.workspace_id}/{branding.logo_digest}/"
    return branding.logo_url


def branding_dict(branding):
    return {
        "brand_name": branding.brand_name,
        "logo_url": logo_url(branding),
        "primary_color": branding.primary_color,
        "sidebar_bg_color": branding.sidebar_bg_color,
        "sidebar_text_color": branding.sidebar_text_color,
        "support_email": branding.support_email,
        "hide_platform_branding": branding.hide_platform_branding,
        "custom_domain_status": branding.custom_domain_status,
        "tls_status": branding.tls_status,
    }


def effective_branding(workspace):
    """A client workspace inherits its agency's branding unless it has its own."""
    for candidate in [workspace, workspace.parent]:
        if candidate is None:
            continue
        branding = WorkspaceBranding.objects.for_workspace(candidate).defer("logo_data").first()
        if branding:
            return {**branding_dict(branding), "custom_domain": branding.custom_domain}
    return {
        **DEFAULT_BRANDING,
        "custom_domain": "",
        "custom_domain_status": WorkspaceBranding.DomainStatus.PENDING,
        "tls_status": WorkspaceBranding.TLSStatus.INACTIVE,
    }


class BrandingSerializer(serializers.ModelSerializer):
    logo = serializers.FileField(write_only=True, required=False)
    workspace_name = serializers.CharField(max_length=100, required=False, write_only=True)

    class Meta:
        model = WorkspaceBranding
        fields = [
            "brand_name",
            "logo_url",
            "primary_color",
            "sidebar_bg_color",
            "sidebar_text_color",
            "logo",
            "workspace_name",
            "support_email",
            "custom_domain",
            "custom_domain_status",
            "verification_token",
            "verified_at",
            "tls_status",
            "hide_platform_branding",
        ]
        read_only_fields = [
            "custom_domain_status",
            "verification_token",
            "verified_at",
            "tls_status",
        ]

    def validate_color(self, value):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise serializers.ValidationError(
                "Enter a color code such as #10244a, or choose a color above."
            )
        return value.lower()

    validate_primary_color = validate_color
    validate_sidebar_bg_color = validate_color
    validate_sidebar_text_color = validate_color

    def validate(self, attrs):
        background = attrs.get(
            "sidebar_bg_color", getattr(self.instance, "sidebar_bg_color", "#ffffff")
        )
        text = attrs.get(
            "sidebar_text_color", getattr(self.instance, "sidebar_text_color", "#41516e")
        )

        def luminance(color):
            channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
            channels = [
                v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels
            ]
            return sum(
                v * weight for v, weight in zip(channels, [0.2126, 0.7152, 0.0722], strict=True)
            )

        light, dark = sorted([luminance(background), luminance(text)], reverse=True)
        if (light + 0.05) / (dark + 0.05) < 4.5:
            raise serializers.ValidationError(
                {
                    "sidebar_text_color": "Choose a text color that is easier to read against your sidebar background."
                }
            )
        return attrs

    def validate_logo(self, value):
        if not 0 < value.size <= 5 * 1024 * 1024:
            raise serializers.ValidationError("Choose an image smaller than 5 MB.")
        data = value.read()
        value.seek(0)
        content_type = (
            "image/png"
            if data.startswith(b"\x89PNG\r\n\x1a\n")
            else "image/jpeg"
            if data.startswith(b"\xff\xd8\xff")
            else "image/gif"
            if data.startswith((b"GIF87a", b"GIF89a"))
            else "image/webp"
            if data.startswith(b"RIFF") and data[8:12] == b"WEBP"
            else ""
        )
        if not content_type:
            raise serializers.ValidationError("Choose a PNG, JPG, GIF or WebP image.")
        return {
            "data": data,
            "content_type": content_type,
            "digest": hashlib.sha256(data).hexdigest(),
        }

    def to_representation(self, instance):
        return {**super().to_representation(instance), "logo_url": logo_url(instance)}

    def _logo_attributes(self, attrs):
        upload = attrs.pop("logo", None)
        if upload:
            attrs.update(
                logo_url="",
                logo_data=upload["data"],
                logo_content_type=upload["content_type"],
                logo_digest=upload["digest"],
            )
        elif "logo_url" in attrs:
            attrs.update(logo_data=b"", logo_content_type="", logo_digest="")
        return attrs

    def create(self, validated_data):
        name = validated_data.pop("workspace_name", None)
        instance = super().create(self._logo_attributes(validated_data))
        if name is not None:
            Workspace.objects.filter(pk=instance.workspace_id).update(name=name)
        return instance

    def update(self, instance, validated_data):
        name = validated_data.pop("workspace_name", None)
        instance = super().update(instance, self._logo_attributes(validated_data))
        if name is not None:
            Workspace.objects.filter(pk=instance.workspace_id).update(name=name)
        return instance

    def validate_logo_url(self, value):
        if value and not value.startswith("https://"):
            raise serializers.ValidationError("Logo must be served over HTTPS.")
        return value

    def validate_custom_domain(self, value):
        value = value.strip().lower()
        if value and not re.fullmatch(r"(?=.{4,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,63}", value):
            raise serializers.ValidationError("Enter a hostname like app.youragency.com.")
        return value


class BrandingView(APIView):
    def get(self, request, workspace_id):
        member = workspace_membership(request, workspace_id)
        own = WorkspaceBranding.objects.for_workspace(workspace_id).defer("logo_data").first()
        return Response(
            {
                "own": BrandingSerializer(own).data if own else None,
                "effective": effective_branding(member.workspace),
                "inherited_from": str(member.workspace.parent_id)
                if not own and member.workspace.parent_id
                else None,
            }
        )

    def put(self, request, workspace_id):
        from .domain_verification import generate_verification_token

        member = workspace_membership(request, workspace_id, ["owner"])
        branding = WorkspaceBranding.objects.for_workspace(workspace_id).defer("logo_data").first()
        prev_domain = branding.custom_domain if branding else ""

        serializer = BrandingSerializer(branding, data=request.data, partial=bool(branding))
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                instance = serializer.save(workspace=member.workspace)
                new_domain = instance.custom_domain
                if new_domain != prev_domain:
                    if new_domain:
                        instance.custom_domain_status = WorkspaceBranding.DomainStatus.PENDING
                        instance.verification_token = generate_verification_token()
                        instance.verified_at = None
                        instance.tls_status = WorkspaceBranding.TLSStatus.INACTIVE
                    else:
                        instance.custom_domain_status = WorkspaceBranding.DomainStatus.PENDING
                        instance.verification_token = ""
                        instance.verified_at = None
                        instance.tls_status = WorkspaceBranding.TLSStatus.INACTIVE
                    instance.save(
                        update_fields=[
                            "custom_domain_status",
                            "verification_token",
                            "verified_at",
                            "tls_status",
                        ]
                    )
        except IntegrityError:
            raise serializers.ValidationError(
                {"custom_domain": "That domain is already in use."}
            ) from None
        audit(member.workspace, request.user, "branding.updated", instance.id)
        return Response(BrandingSerializer(instance).data)

    def delete(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner"])
        WorkspaceBranding.objects.for_workspace(workspace_id).delete()
        audit(member.workspace, request.user, "branding.reset", workspace_id)
        return Response(status=204)


class PublicWorkspaceLogoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def get(self, request, workspace_id, digest):
        image = get_object_or_404(
            WorkspaceBranding.all_objects, workspace_id=workspace_id, logo_digest=digest
        )
        if not image.logo_data or image.logo_content_type not in {
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
        }:
            from django.http import Http404

            raise Http404
        etag = f'"{image.logo_digest}"'
        response = (
            HttpResponseNotModified()
            if request.headers.get("If-None-Match") == etag
            else HttpResponse(bytes(image.logo_data), content_type=image.logo_content_type)
        )
        response["ETag"] = etag
        response["Cache-Control"] = "public, max-age=86400, immutable"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response


class VerifyDomainView(APIView):
    """Explicit domain verification trigger by workspace owners or admins."""

    def post(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        branding = WorkspaceBranding.objects.for_workspace(workspace_id).first()
        if not branding or not branding.custom_domain:
            return Response(
                {"error": "no_custom_domain", "detail": "No custom domain configured."},
                status=400,
            )
        from .domain_verification import verify_custom_domain

        success, message = verify_custom_domain(branding, user=request.user)
        return Response(
            {
                "verified": success,
                "message": message,
                "branding": BrandingSerializer(branding).data,
            },
            status=200 if success else 400,
        )


class PublicBrandingView(APIView):
    """Resolves the branding for the host the browser is on (custom domains)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def get(self, request):
        host = (request.headers.get("X-Forwarded-Host") or request.get_host()).split(":")[0].lower()
        branding = WorkspaceBranding.all_objects.filter(custom_domain=host).first()
        return Response(
            {**branding_dict(branding), "custom_domain": host}
            if branding
            else {**DEFAULT_BRANDING, "custom_domain": ""}
        )


class ClientWorkspaceSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()

    def get_members(self, obj):
        return Membership.objects.for_workspace(obj).count()

    class Meta:
        model = Workspace
        fields = ["id", "name", "created_at", "members"]
        read_only_fields = ["id", "created_at", "members"]


class ClientWorkspaceList(APIView):
    """An agency workspace creates and lists the client workspaces it manages."""

    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        clients = Workspace.objects.filter(parent_id=workspace_id).order_by("created_at")
        return Response(ClientWorkspaceSerializer(clients, many=True).data)

    @transaction.atomic
    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        if member.workspace.parent_id:
            raise serializers.ValidationError("Client workspaces cannot manage clients.")
        serializer = ClientWorkspaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if Workspace.objects.filter(parent_id=workspace_id).count() >= 200:
            raise serializers.ValidationError("Client workspace limit reached.")
        client = create_workspace(request.user, serializer.validated_data["name"])
        client.parent = member.workspace
        client.save(update_fields=["parent"])
        audit(member.workspace, request.user, "client_workspace.created", client.id)
        return Response(ClientWorkspaceSerializer(client).data, status=201)
