import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Invitation, Membership, Workspace
from .permissions import workspace_membership
from .services import audit

INVITATION_TTL = timedelta(days=7)


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def open_invitations(workspace_id):
    return Invitation.objects.for_workspace(workspace_id).filter(
        accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now()
    )


class InvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "expires_at", "created_at"]
        read_only_fields = ["id", "expires_at", "created_at"]

    def validate_email(self, value):
        return value.strip().lower()


class InvitationListView(generics.ListCreateAPIView):
    serializer_class = InvitationSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return open_invitations(self.kwargs["workspace_id"])

    def create(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email, role = serializer.validated_data["email"], serializer.validated_data["role"]
        if role == "admin" and member.role != "owner":
            raise PermissionDenied("Only the owner can invite admins.")
        token = secrets.token_urlsafe(32)
        with transaction.atomic():
            # Seat accounting is serialized per workspace; open invitations hold a seat.
            Workspace.objects.select_for_update().get(pk=workspace_id)
            members = Membership.objects.for_workspace(workspace_id)
            if members.filter(user__email__iexact=email).exists():
                raise serializers.ValidationError("This person is already a member.")
            # Reissuing to the same address replaces the earlier link.
            open_invitations(workspace_id).filter(email__iexact=email).update(
                revoked_at=timezone.now()
            )
            from apps.billing.gating import check_within_limit

            check_within_limit(workspace_id, "team_seats")
            invitation = Invitation.objects.for_workspace(workspace_id).create(
                workspace=member.workspace,
                email=email,
                role=role,
                token_hash=token_digest(token),
                invited_by=request.user,
                expires_at=timezone.now() + INVITATION_TTL,
            )
            audit(member.workspace, request.user, "invitation.created", invitation.id, role=role)
        data = InvitationSerializer(invitation).data
        # No email delivery exists yet: the raw token is returned once, to the inviter only.
        data["accept_url"] = f"{settings.PUBLIC_APP_URL}/?invite={token}"
        return Response(data, status=status.HTTP_201_CREATED)


class InvitationDetailView(APIView):
    @transaction.atomic
    def delete(self, request, workspace_id, invitation_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        invitation = get_object_or_404(
            open_invitations(workspace_id).select_for_update(), pk=invitation_id
        )
        if invitation.role == "admin" and member.role != "owner":
            raise PermissionDenied("Only the owner can revoke admin invitations.")
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
        audit(member.workspace, request.user, "invitation.revoked", invitation.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AcceptInvitationView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        token = request.data.get("token")
        if not isinstance(token, str) or not 1 <= len(token) <= 200:
            raise serializers.ValidationError("This invitation is invalid or has expired.")
        # Global lookup only locates the tenant; locks are then taken workspace-first,
        # the same order as invitation creation, to avoid deadlocks.
        found = Invitation.all_objects.filter(token_hash=token_digest(token)).first()
        if not found:
            raise serializers.ValidationError("This invitation is invalid or has expired.")
        with transaction.atomic():
            workspace = Workspace.objects.select_for_update().get(pk=found.workspace_id)
            invitation = (
                open_invitations(workspace.pk).select_for_update().filter(pk=found.pk).first()
            )
            if not invitation:
                raise serializers.ValidationError("This invitation is invalid or has expired.")
            if invitation.email.lower() != request.user.email.lower():
                raise serializers.ValidationError(
                    "This invitation was sent to a different email address."
                )
            members = Membership.objects.for_workspace(workspace)
            if members.filter(user=request.user).exists():
                raise serializers.ValidationError("You are already a member of this workspace.")
            from apps.billing.gating import check_within_limit

            # The invitation itself holds one of the open slots, so count members only.
            check_within_limit(workspace.pk, "team_seats", current=members.count())
            membership = members.create(
                workspace=workspace, user=request.user, role=invitation.role
            )
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=["accepted_at"])
            audit(
                workspace, request.user, "invitation.accepted", membership.id, role=membership.role
            )
        return Response(
            {"workspace_id": workspace.pk, "role": membership.role}, status=status.HTTP_201_CREATED
        )
