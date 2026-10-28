import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    email = models.EmailField(unique=True)
    # Set only through `platform_ops.accounts.ban_user`, which also blocks sign-in and
    # pauses every workspace the user owns. A flag on its own is not a ban.
    is_banned = models.BooleanField(default=False)
    banned_at = models.DateTimeField(null=True, blank=True)
    ban_reason = models.CharField(max_length=300, blank=True)
    # Proof the signup controls this address. Null until confirmed; see
    # tenants.verification for what it gates.
    email_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_ci_unique")]


# App Store apps a workspace can pin; the client catalog uses the same IDs.
PINNABLE_APPS = ("bio", "calendar", "shield", "deeplinks", "webchat", "forms", "creator-kit")


def default_pinned_apps():
    return ["bio", "calendar"]


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    # Agency (reseller) that manages this workspace; data isolation is unchanged.
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="clients"
    )
    # App Store apps shown in the sidebar dock, in order. Shared by every member.
    pinned_apps = models.JSONField(default=default_pinned_apps, blank=True)

    class Meta:
        ordering = ["created_at", "id"]


def check_tenant_links(model, objs, fields=None):
    """Every tenant FK on these rows must reference a row in the same workspace.
    `save()` checks one row; bulk writes skip `save()`, so they come through here with
    one query per FK field instead of one per row. PostgreSQL also enforces this with
    triggers (tenants/isolation.py); this gives the same answer on SQLite and a clear
    error before the write."""
    from django.core.exceptions import ValidationError

    objs = list(objs)
    for field in model._meta.concrete_fields:
        related = getattr(field, "related_model", None)
        if field.name == "workspace" or not related or not issubclass(related, TenantModel):
            continue
        if fields is not None and field.name not in fields and "workspace" not in fields:
            continue
        values = {getattr(obj, field.attname) for obj in objs} - {None}
        if not values:
            continue
        owners = dict(related.all_objects.filter(pk__in=values).values_list("pk", "workspace_id"))
        for obj in objs:
            value = getattr(obj, field.attname)
            if value is not None and owners.get(value) != obj.workspace_id:
                raise ValidationError("Related records must belong to this workspace.")
    return objs


class TenantQuerySet(models.QuerySet):
    def bulk_create(self, objs, *args, **kwargs):
        return super().bulk_create(check_tenant_links(self.model, objs), *args, **kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        return super().bulk_update(
            check_tenant_links(self.model, objs, set(fields)), fields, *args, **kwargs
        )


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
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
    all_objects = models.Manager.from_queryset(TenantQuerySet)()

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
    class DomainStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        FAILED = "failed", "Failed"

    class TLSStatus(models.TextChoices):
        INACTIVE = "inactive", "Inactive"
        ISSUING = "issuing", "Issuing"
        ACTIVE = "active", "Active"
        ERROR = "error", "Error"

    brand_name = models.CharField(max_length=60)
    logo_url = models.URLField(max_length=2000, blank=True)
    primary_color = models.CharField(max_length=7, default="#10244a")
    sidebar_bg_color = models.CharField(max_length=7, default="#ffffff")
    sidebar_text_color = models.CharField(max_length=7, default="#41516e")
    logo_data = models.BinaryField(default=bytes, blank=True)
    logo_content_type = models.CharField(max_length=30, blank=True)
    logo_digest = models.CharField(max_length=64, blank=True)
    support_email = models.EmailField(blank=True)
    custom_domain = models.CharField(max_length=253, blank=True)
    custom_domain_status = models.CharField(
        max_length=20, choices=DomainStatus.choices, default=DomainStatus.PENDING
    )
    verification_token = models.CharField(max_length=64, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    tls_status = models.CharField(
        max_length=20, choices=TLSStatus.choices, default=TLSStatus.INACTIVE
    )
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
