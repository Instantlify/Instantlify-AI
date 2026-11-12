import uuid

from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from .models import AuditEvent, Membership, Workspace
from .permissions import workspace_membership
from .profile import ProfileSerializer, photo_url
from .serializers import (
    AuditSerializer,
    LoginSerializer,
    MembershipSerializer,
    SignupSerializer,
    WorkspaceSerializer,
)
from .services import audit, create_workspace


class CSRFView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    # The client fetches a token before every write, and with no authentication here
    # each call would count against the per-IP anonymous rate: a busy signed-in user
    # (or an office behind one IP) would be locked out of saving anything.
    throttle_classes = []

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class SignupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(
                    username=str(uuid.uuid4()),
                    email=data["email"],
                    first_name=data["name"],
                    password=data["password"],
                )
        except IntegrityError:
            return Response(
                {"detail": "Unable to create this account. Try signing in."}, status=400
            )
        from .verification import send_verification

        send_verification(user)
        # Close the marketing loop: this signup belongs to the visit session that
        # produced it, so a landing page's conversion is measurable end to end.
        # Tracking must never be able to fail a signup.
        try:
            from apps.platform_ops import growth

            growth.record_page_signup(
                session_id=growth.session_key(request),
                page=str(request.data.get("landing_page", "/"))[:200],
                user=user,
            )
        except Exception:  # noqa: BLE001 - attribution is best effort, signup is not
            pass
        return Response(
            {
                "id": user.id,
                "name": user.first_name,
                "email": user.email,
                "email_verified": False,
            },
            status=201,
        )


@method_decorator(csrf_protect, name="dispatch")
class LoginView(SignupView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        candidate = get_user_model().objects.filter(email__iexact=data["email"]).first()
        user = authenticate(
            request, username=candidate.username if candidate else "", password=data["password"]
        )
        if user is None:
            return Response({"detail": "Email or password is incorrect."}, status=401)
        login(request, user)
        return Response(
            {
                "id": user.id,
                "name": user.first_name,
                "email": user.email,
                "email_verified": bool(user.email_verified_at),
            }
        )


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(
            {
                "id": request.user.id,
                "name": request.user.first_name,
                "email": request.user.email,
                "email_verified": bool(request.user.email_verified_at),
                "photo_url": photo_url(request.user),
            }
        )

    def patch(self, request):
        serializer = ProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        email_changed = False
        try:
            with transaction.atomic():
                user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
                if "name" in data:
                    user.first_name = data["name"]
                if "email" in data and data["email"] != user.email:
                    user.email = data["email"]
                    user.email_verified_at = None
                    email_changed = True
                user.save(update_fields=["first_name", "email", "email_verified_at"])
                if "photo" in data:
                    from .models import ProfilePhoto

                    ProfilePhoto.objects.update_or_create(user=user, defaults=data["photo"])
        except IntegrityError:
            raise serializers.ValidationError(
                {"email": "This email address is already in use."}
            ) from None
        if email_changed:
            from .verification import send_verification

            send_verification(user)
        return Response(
            {
                "id": user.id,
                "name": user.first_name,
                "email": user.email,
                "email_verified": bool(user.email_verified_at),
                "photo_url": photo_url(user),
            }
        )


class PasswordChangeView(APIView):
    @transaction.atomic
    def post(self, request):
        password = serializers.CharField(max_length=128, trim_whitespace=False).run_validation(
            request.data.get("password")
        )
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        try:
            validate_password(password, user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from None
        user.set_password(password)
        user.save(update_fields=["password"])
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        update_session_auth_hash(request, user)
        return Response({"detail": "Password updated successfully."})


class JWTLoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        # API clients use email; Django's internal username is never public.
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        candidate = get_user_model().objects.filter(email__iexact=data["email"]).first()
        token_serializer = self.get_serializer(
            data={"username": candidate.username if candidate else "", "password": data["password"]}
        )
        token_serializer.is_valid(raise_exception=True)
        return Response(token_serializer.validated_data)


class JWTRefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class JWTRevokeView(TokenBlacklistView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class WorkspaceListView(generics.ListCreateAPIView):
    serializer_class = WorkspaceSerializer

    def get_queryset(self):
        return Workspace.objects.filter(membership__user=self.request.user)

    def perform_create(self, serializer):
        serializer.instance = create_workspace(
            self.request.user, serializer.validated_data["name"], checkout_pending=True
        )


class WorkspaceDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = WorkspaceSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        roles = ["owner", "admin"] if self.request.method == "PATCH" else None
        member = workspace_membership(
            self.request, self.kwargs["workspace_id"], roles, allow_pending=True
        )
        return member.workspace

    @transaction.atomic
    def perform_update(self, serializer):
        workspace = serializer.save()
        audit(workspace, self.request.user, "workspace.updated", workspace.id)


class MembershipListView(generics.ListAPIView):
    serializer_class = MembershipSerializer

    def get_queryset(self):
        membership = workspace_membership(self.request, self.kwargs["workspace_id"])
        return Membership.objects.for_workspace(membership.workspace).select_related("user")


class MembershipDetailView(APIView):
    @transaction.atomic
    def patch(self, request, workspace_id, membership_id):
        owner = workspace_membership(request, workspace_id, ["owner"])
        member = get_object_or_404(
            Membership.objects.for_workspace(owner.workspace).select_for_update(), pk=membership_id
        )
        serializer = MembershipSerializer(member, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if member.role == "owner" or serializer.validated_data.get("role") == "owner":
            raise PermissionDenied("Ownership transfer requires a dedicated workflow.")
        member = serializer.save()
        audit(owner.workspace, request.user, "membership.role_changed", member.id, role=member.role)
        return Response(serializer.data)

    @transaction.atomic
    def delete(self, request, workspace_id, membership_id):
        from apps.crm.models import Conversation, Lead

        actor = workspace_membership(request, workspace_id, allow_viewer_write=True)
        member = get_object_or_404(
            Membership.objects.for_workspace(actor.workspace).select_for_update(), pk=membership_id
        )
        if member.role == "owner":
            raise PermissionDenied("The owner cannot be removed.")
        if actor.role == "viewer" and member.user_id != request.user.id:
            raise PermissionDenied("Viewers have read-only access.")
        leaving = member.user_id == request.user.id
        if not (
            leaving
            or actor.role == "owner"
            or (actor.role == "admin" and member.role in {"agent", "viewer"})
        ):
            raise PermissionDenied("Your role cannot remove this member.")
        # Removed members lose access; their conversations return to the shared queue.
        Conversation.objects.for_workspace(actor.workspace).filter(
            assigned_to_id=member.user_id
        ).update(assigned_to=None)
        Lead.objects.for_workspace(actor.workspace).filter(assigned_to_id=member.user_id).update(
            assigned_to=None
        )
        member.delete()
        audit(actor.workspace, request.user, "membership.removed", member.id, role=member.role)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AuditListView(generics.ListAPIView):
    serializer_class = AuditSerializer

    def get_queryset(self):
        membership = workspace_membership(
            self.request, self.kwargs["workspace_id"], ["owner", "admin"]
        )
        return AuditEvent.objects.for_workspace(membership.workspace)
