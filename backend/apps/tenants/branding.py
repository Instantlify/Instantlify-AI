"""White-label: agencies own client workspaces and brand the app they see."""

import re

from django.db import IntegrityError, transaction
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
    "primary_color": "#347359",
    "support_email": "",
    "hide_platform_branding": False,
}


def branding_dict(branding):
    return {
        "brand_name": branding.brand_name,
        "logo_url": branding.logo_url,
        "primary_color": branding.primary_color,
        "support_email": branding.support_email,
        "hide_platform_branding": branding.hide_platform_branding,
    }


def effective_branding(workspace):
    """A client workspace inherits its agency's branding unless it has its own."""
    for candidate in [workspace, workspace.parent]:
        if candidate is None:
            continue
        branding = WorkspaceBranding.objects.for_workspace(candidate).first()
        if branding:
            return {**branding_dict(branding), "custom_domain": branding.custom_domain}
    return {**DEFAULT_BRANDING, "custom_domain": ""}


class BrandingSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceBranding
        fields = [
            "brand_name",
            "logo_url",
            "primary_color",
            "support_email",
            "custom_domain",
            "hide_platform_branding",
        ]

    def validate_primary_color(self, value):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise serializers.ValidationError("Use a hex colour like #347359.")
        return value.lower()

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
        own = WorkspaceBranding.objects.for_workspace(workspace_id).first()
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
        member = workspace_membership(request, workspace_id, ["owner"])
        branding = WorkspaceBranding.objects.for_workspace(workspace_id).first()
        serializer = BrandingSerializer(branding, data=request.data, partial=bool(branding))
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                branding = serializer.save(workspace=member.workspace)
        except IntegrityError:
            raise serializers.ValidationError(
                {"custom_domain": "That domain is already in use."}
            ) from None
        audit(member.workspace, request.user, "branding.updated", branding.id)
        return Response(BrandingSerializer(branding).data)

    def delete(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner"])
        WorkspaceBranding.objects.for_workspace(workspace_id).delete()
        audit(member.workspace, request.user, "branding.reset", workspace_id)
        return Response(status=204)


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
