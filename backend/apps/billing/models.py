from django.db import models
from django.utils import timezone

from apps.tenants.crypto import EncryptedTextField
from apps.tenants.models import TenantModel


class BillingAccount(TenantModel):
    customer_id = models.CharField(max_length=100, null=True, unique=True)
    subscription_id = models.CharField(max_length=100, blank=True)
    plan = models.CharField(max_length=20, default="free")
    status = models.CharField(max_length=30, default="trialing")
    period_start = models.DateTimeField(default=timezone.now)
    period_end = models.DateTimeField(null=True)
    usage_limit = models.PositiveIntegerField(default=100)
    seat_limit = models.PositiveIntegerField(default=1)
    channel_limit = models.PositiveIntegerField(default=1)
    last_event_created = models.BigIntegerField(default=0)
    # From the Stripe subscription: "monthly" / "annual" ("" when unknown or free).
    billing_interval = models.CharField(max_length=10, blank=True)
    trial_ends_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_billing_account")]


class BillingEvent(TenantModel):
    event_id = models.CharField(max_length=150, unique=True)
    payload = EncryptedTextField()
    status = models.CharField(max_length=20, default="pending")


class Offer(TenantModel):
    """Something a workspace sells in-chat. Amounts live here, never in the model's output."""

    name = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True)
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="usd")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_cents__gte=50), name="offer_min_amount"
            )
        ]


class Payment(TenantModel):
    """A checkout the agent (or a human) sent to a lead, on the workspace's own Stripe."""

    offer = models.ForeignKey(Offer, on_delete=models.PROTECT)
    conversation = models.ForeignKey("crm.Conversation", on_delete=models.CASCADE)
    lead = models.ForeignKey("crm.Lead", on_delete=models.CASCADE)
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="usd")
    status = models.CharField(max_length=20, default="pending")
    checkout_session_id = models.CharField(max_length=120, blank=True)
    checkout_url = EncryptedTextField(blank=True)
    idempotency_key = models.CharField(max_length=255)
    paid_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "idempotency_key"], name="unique_payment_intent"
            )
        ]


class BillingJob(TenantModel):
    kind = models.CharField(max_length=20)
    plan = models.CharField(max_length=20, blank=True)
    request_key = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="pending")
    result = EncryptedTextField(default="{}")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "request_key"], name="unique_billing_request"
            )
        ]
