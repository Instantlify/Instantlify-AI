import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    email = models.EmailField(unique=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_ci_unique")]


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    # Agency (reseller) that manages this workspace; data isolation is unchanged.
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="clients"
    )

    class Meta:
        ordering = ["created_at", "id"]


class TenantManager(models.Manager):
    """Unqualified reads fail closed. Services explicitly select their tenant."""

    def get_queryset(self):
        return super().get_queryset().none()

    def for_workspace(self, workspace):
        if workspace is None:
            raise ValueError("A workspace is required")
        return super().get_queryset().filter(workspace_id=getattr(workspace, "pk", workspace))


class TenantModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = TenantManager()
    # Reserved for auth membership lookup, explicit operational fan-out, migrations.
    all_objects = models.Manager()

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        for field in self._meta.fields:
            related = getattr(field, "related_model", None)
            value = getattr(self, field.attname, None)
            if related and issubclass(related, TenantModel) and value is not None:
                if not related.all_objects.filter(
                    pk=value, workspace_id=self.workspace_id
                ).exists():
                    raise ValidationError("Related records must belong to this workspace.")
        return super().save(*args, **kwargs)

    class Meta:
        abstract = True


class Membership(TenantModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        AGENT = "agent", "Agent"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.AGENT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="unique_workspace_member"),
            models.UniqueConstraint(
                fields=["workspace"], condition=models.Q(role="owner"), name="one_workspace_owner"
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=["owner", "admin", "agent"]),
                name="valid_membership_role",
            ),
        ]
        ordering = ["created_at", "id"]


class WorkspaceBranding(TenantModel):
    brand_name = models.CharField(max_length=60)
    logo_url = models.URLField(max_length=2000, blank=True)
    primary_color = models.CharField(max_length=7, default="#347359")
    support_email = models.EmailField(blank=True)
    custom_domain = models.CharField(max_length=253, blank=True)
    hide_platform_branding = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace"], name="one_branding_per_workspace"),
            models.UniqueConstraint(
                fields=["custom_domain"],
                condition=~models.Q(custom_domain=""),
                name="unique_custom_domain",
            ),
        ]


class Invitation(TenantModel):
    """Single-use, email-bound invite. Only the token's SHA-256 digest is stored."""

    email = models.EmailField()
    role = models.CharField(max_length=10, choices=[("admin", "Admin"), ("agent", "Agent")])
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["admin", "agent"]), name="valid_invitation_role"
            )
        ]


class AuditEvent(TenantModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    target_id = models.CharField(max_length=100, blank=True)
    # Deliberately no arbitrary input/output blob: allowlisted metadata at service boundary.
    metadata = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["workspace", "created_at"])]


class OutboxEvent(TenantModel):
    kind = models.CharField(max_length=80)
    processed_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [models.Index(fields=["processed_at", "created_at"])]


class DataOperation(TenantModel):
    kind = models.CharField(max_length=20)
    status = models.CharField(max_length=20, default="pending")
    error_code = models.CharField(max_length=50, blank=True)
    # Export archives contain customer data and are encrypted at rest.
    from .crypto import EncryptedTextField

    result = EncryptedTextField(blank=True)
