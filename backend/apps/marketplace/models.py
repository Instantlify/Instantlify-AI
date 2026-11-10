from django.db import models

from apps.tenants.crypto import EncryptedTextField
from apps.tenants.models import TenantModel


class Template(TenantModel):
    """A published automation graph other workspaces can install.

    The owning workspace is the author. Graphs are re-validated on install, so a
    template can never put an unpublishable flow into another tenant."""

    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True, max_length=2000)
    category = models.CharField(max_length=40, default="sales")
    graph = models.JSONField()
    author_name = models.CharField(max_length=100, blank=True)
    price_cents = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, default="published")
    install_count = models.PositiveIntegerField(default=0)
    source_automation_id = models.UUIDField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-install_count", "-created_at"]
        indexes = [models.Index(fields=["status", "category"])]


class TemplateInstall(TenantModel):
    """Installer-side record; `template_id` is a plain UUID because it crosses tenants."""

    template_id = models.UUIDField()
    automation = models.ForeignKey("automations.Automation", on_delete=models.CASCADE)


class SellerAccount(TenantModel):
    """The author's Stripe Connect recipient account (Accounts v2, express dashboard).

    Instantlify is the merchant of record for template sales: buyers pay on the platform
    account and the author's share is transferred by destination charge. Only the
    account ID and the last observed capability status are stored here."""

    stripe_account_id = models.CharField(max_length=100, unique=True)
    country = models.CharField(max_length=2, default="us")
    # `stripe_transfers` capability status as reported by Stripe: active/pending/restricted.
    transfers_status = models.CharField(max_length=20, default="pending")
    requirements_due = models.BooleanField(default=True)
    checked_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace"], name="one_seller_account_per_workspace")
        ]


class TemplatePurchase(TenantModel):
    """Buyer-side record of a paid template checkout. Cross-tenant IDs are plain UUIDs."""

    STATUSES = ["pending", "paid", "installed", "expired", "failed"]

    template_id = models.UUIDField()
    seller_workspace_id = models.UUIDField()
    title = models.CharField(max_length=120)
    amount_cents = models.PositiveIntegerField()
    fee_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="usd")
    status = models.CharField(max_length=20, default="pending")
    checkout_session_id = models.CharField(max_length=120, blank=True)
    checkout_url = EncryptedTextField(blank=True)
    idempotency_key = models.CharField(max_length=255)
    paid_at = models.DateTimeField(null=True)
    automation = models.ForeignKey("automations.Automation", null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "idempotency_key"], name="unique_template_purchase_intent"
            ),
            # A buyer pays for a template at most once; later installs are free.
            models.UniqueConstraint(
                fields=["workspace", "template_id"],
                condition=models.Q(status__in=["paid", "installed"]),
                name="one_paid_purchase_per_template",
            ),
        ]
        indexes = [models.Index(fields=["status", "created_at"])]
