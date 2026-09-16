import uuid

from django.conf import settings
from django.db import models

from apps.tenants.crypto import EncryptedTextField


class PlatformRole(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField(
        max_length=20,
        choices=[("owner", "Owner"), ("support", "Support"), ("analyst", "Read-only analyst")],
    )
    active = models.BooleanField(default=True)
    otp_secret = EncryptedTextField(blank=True)
    otp_confirmed = models.BooleanField(default=False)
    last_counter = models.BigIntegerField(default=-1)
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True)
    version = models.PositiveIntegerField(default=1)


class Control(models.Model):
    # An empty scope means platform-wide; otherwise an exact workspace UUID.
    scope = models.CharField(max_length=36, blank=True)
    key = models.CharField(max_length=100)
    disabled = models.BooleanField(default=True)
    reason = models.CharField(max_length=300)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "key"], name="unique_platform_control")
        ]


class PlatformAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.CharField(max_length=36)
    action = models.CharField(max_length=80)
    workspace_id = models.CharField(max_length=36, blank=True)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Platform audit entries are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Platform audit entries are immutable")


class SupportSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operator = models.ForeignKey(PlatformRole, on_delete=models.PROTECT)
    workspace = models.ForeignKey("tenants.Workspace", on_delete=models.CASCADE)
    reason = models.CharField(max_length=300)
    expires_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True)


class PlatformInvite(models.Model):
    email = models.EmailField()
    role = models.CharField(max_length=20)
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)


class OperationStatus(models.Model):
    provider = models.CharField(max_length=30, unique=True)
    review_status = models.CharField(max_length=100, default="Not verified")
    permissions = models.CharField(max_length=1000, blank=True)
    certificate_expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class DailyMetric(models.Model):
    day = models.DateField()
    name = models.CharField(max_length=80)
    value = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["day", "name"], name="unique_ops_daily_metric")
        ]


class SubscriptionSnapshot(models.Model):
    workspace = models.ForeignKey("tenants.Workspace", on_delete=models.CASCADE)
    day = models.DateField()
    currency = models.CharField(max_length=3)
    monthly_cents = models.DecimalField(max_digits=18, decimal_places=4)
    status = models.CharField(max_length=30)
    overage = models.PositiveIntegerField(default=0)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "day", "currency"], name="unique_subscription_snapshot"
            )
        ]
