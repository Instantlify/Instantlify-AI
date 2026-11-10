import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import PINNABLE_APPS, AuditEvent, Membership, Workspace


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    name = serializers.CharField(max_length=150)

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        user = get_user_model()(
            email=attrs["email"], first_name=attrs["name"], username=str(uuid.uuid4())
        )
        try:
            validate_password(attrs["password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class WorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    def get_role(self, obj):
        return Membership.objects.for_workspace(obj).get(user=self.context["request"].user).role

    allowed_sections = serializers.SerializerMethodField()

    def get_allowed_sections(self, obj):
        member = Membership.objects.for_workspace(obj).get(user=self.context["request"].user)
        return [] if member.role == "owner" else member.allowed_sections

    branding = serializers.SerializerMethodField()

    def get_branding(self, obj):
        from .branding import effective_branding

        return effective_branding(obj)

    def validate_pinned_apps(self, value):
        if (
            not isinstance(value, list)
            or len(set(value)) != len(value)
            or any(item not in PINNABLE_APPS for item in value)
        ):
            raise serializers.ValidationError("Pin each available app at most once.")
        return value

    class Meta:
        model = Workspace
        fields = [
            "id",
            "name",
            "created_at",
            "role",
            "parent",
            "branding",
            "pinned_apps",
            "checkout_pending",
            "allowed_sections",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "role",
            "parent",
            "branding",
            "checkout_pending",
            "allowed_sections",
        ]


class MembershipSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.first_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Membership
        fields = [
            "id",
            "user_id",
            "name",
            "email",
            "role",
            "allowed_sections",
            "allowed_connections",
            "created_at",
        ]
        read_only_fields = ["id", "user_id", "name", "email", "created_at"]

    def validate(self, attrs):
        from .access import validate_access

        if "allowed_sections" in attrs or "allowed_connections" in attrs:
            instance = self.instance
            sections, connections = validate_access(
                instance.workspace_id,
                attrs.get("allowed_sections", instance.allowed_sections),
                attrs.get("allowed_connections", instance.allowed_connections),
            )
            attrs["allowed_sections"], attrs["allowed_connections"] = sections, connections
        return attrs


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["id", "action", "actor_id", "target_id", "metadata", "created_at"]
        read_only_fields = fields
