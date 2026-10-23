from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.tenants.crypto import EncryptedTextField
from apps.tenants.models import TenantModel

INTERVALS = [("monthly", "Monthly"), ("annual", "Annual")]


class Plan(models.Model):
    """A pricing tier, interval-agnostic. Prices live on PlanPrice, limits on PlanLimits.
    Tiers are never deleted once sold: retire them with is_active=False and keep serving
    existing subscribers."""

    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=60)
    is_featured = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    # Custom tiers (partner deals, lifetime cohorts, legacy grandfathers) are editable
    # from the console; default public tiers change through a migration.
    is_custom = models.BooleanField(default=False)
    partner_label = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "slug"]

    def __str__(self):
        return self.slug

    @property
    def limits(self):
        limits, _ = PlanLimits.objects.get_or_create(plan=self)
        return limits


class PlanPrice(models.Model):
    """One row per (plan, interval). Annual is set explicitly, never derived."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="prices")
    billing_interval = models.CharField(max_length=10, choices=INTERVALS)
    price_cents = models.PositiveIntegerField(default=0)
    stripe_price_id = models.CharField(max_length=100, blank=True)
    # Metered overage price billed alongside this base price, when the tier has one.
    stripe_meter_price_id = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "billing_interval"], name="one_price_per_interval"
            )
        ]
        ordering = ["plan__sort_order", "billing_interval"]

    @property
    def dollars(self):
        return f"{self.price_cents / 100:,.2f}"


class PlanLimits(models.Model):
    """What a tier allows. Null on a numeric limit means unlimited."""

    plan = models.OneToOneField(Plan, on_delete=models.CASCADE, related_name="limit_row")
    # Connected channel accounts of any provider (named after the brief's first channel).
    max_instagram_accounts = models.PositiveIntegerField(null=True, blank=True)
    max_contacts = models.PositiveIntegerField(null=True, blank=True)
    team_seats = models.PositiveIntegerField(null=True, blank=True)
    # Customer-facing AI generations per billing period.
    max_ai_messages = models.PositiveIntegerField(null=True, blank=True)
    ai_agent_enabled = models.BooleanField(default=False)
    integrations_unlocked = models.BooleanField(default=False)
    content_scheduling_enabled = models.BooleanField(default=False)
    voice_notes_enabled = models.BooleanField(default=False)

    NUMERIC = ["max_instagram_accounts", "max_contacts", "team_seats", "max_ai_messages"]
    FLAGS = [
        "ai_agent_enabled",
        "integrations_unlocked",
        "content_scheduling_enabled",
        "voice_notes_enabled",
    ]

    def as_dict(self):
        return {name: getattr(self, name) for name in self.NUMERIC + self.FLAGS}


def default_plan():
    return Plan.objects.get(slug=settings.DEFAULT_PLAN_SLUG)


class BillingAccount(TenantModel):
    """The workspace's subscription record (the brief's `Subscription`): Stripe customer
    and subscription IDs, status and period, and the PlanPrice it is on. Limits are never
    stored here; they come from the plan so a tier edit applies to every subscriber."""

    customer_id = models.CharField(max_length=100, null=True, unique=True)
    subscription_id = models.CharField(max_length=100, blank=True)
    # Null means the default (free) plan. PROTECT: a tier with subscribers cannot vanish.
    plan_price = models.ForeignKey(PlanPrice, null=True, blank=True, on_delete=models.PROTECT)
    # Stripe bills a price this deployment does not map; limits are left as they were.
    price_unmapped = models.BooleanField(default=False)
    status = models.CharField(max_length=30, default="trialing")
    period_start = models.DateTimeField(default=timezone.now)
    period_end = models.DateTimeField(null=True)
    last_event_created = models.BigIntegerField(default=0)
    # From the Stripe subscription: "monthly" / "annual" ("" when unknown or free).
    billing_interval = models.CharField(max_length=10, blank=True)
    trial_ends_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_billing_account")]

    @property
    def plan_obj(self):
        return self.plan_price.plan if self.plan_price_id else default_plan()

    @property
    def plan(self):
        return "unmapped" if self.price_unmapped else self.plan_obj.slug

    @property
    def limits(self):
        return self.plan_obj.limits

    # Compatibility names used across the codebase; None means unlimited.
    @property
    def seat_limit(self):
        return self.limits.team_seats

    @property
    def channel_limit(self):
        return self.limits.max_instagram_accounts

    @property
    def usage_limit(self):
        return self.limits.max_ai_messages


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
    plan = models.CharField(max_length=40, blank=True)
    interval = models.CharField(max_length=10, default="monthly")
    # Credit top-ups (kind="credits").
    amount_cents = models.PositiveIntegerField(default=0)
    # "onboarding" sends Stripe back to the signup wizard instead of Settings.
    return_to = models.CharField(max_length=20, blank=True)
    request_key = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="pending")
    result = EncryptedTextField(default="{}")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "request_key"], name="unique_billing_request"
            )
        ]


# ---------------------------------------------------------------- prepaid AI credits (2.10)


class ModelPricingRate(models.Model):
    """Platform-wide rate card, in cents per million tokens. `model_pattern` uses `%` as a
    wildcard (`claude-opus%`); the most specific match wins and the single fallback row
    prices anything unrecognised so billing never charges zero or crashes."""

    model_pattern = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=100, blank=True)
    our_input = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    our_output = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    our_cache_read = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    our_cache_write = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    real_input = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    real_output = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    real_cache_read = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    real_cache_write = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    is_fallback_default = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["is_fallback_default", "model_pattern"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_fallback_default"],
                condition=models.Q(is_fallback_default=True),
                name="one_fallback_pricing_rate",
            )
        ]

    RATE_FIELDS = ["input", "output", "cache_read", "cache_write"]

    def margin(self):
        """Blended our/real multiplier on a 3:1 input:output mix; None when real is zero."""
        real = self.real_input * 3 + self.real_output
        if not real:
            return None
        return round(float((self.our_input * 3 + self.our_output) / real), 2)


class AICreditBalance(TenantModel):
    """Prepaid balance per workspace, in cents with sub-cent precision so tiny calls
    still accumulate. Auto top-up charges the saved card off-session and disables
    itself after one failure."""

    balance_cents = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    auto_topup_enabled = models.BooleanField(default=False)
    auto_topup_threshold_cents = models.PositiveIntegerField(default=500)
    auto_topup_amount_cents = models.PositiveIntegerField(default=2000)
    payment_method_id = models.CharField(max_length=100, blank=True)
    auto_topup_failed_at = models.DateTimeField(null=True)
    topup_attempts = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_credit_balance")]


class AICreditTransaction(TenantModel):
    """The ledger. Signed amounts (usage negative), the real provider cost next to the
    charged amount so margin is visible per row, and the balance after the row."""

    TYPES = ["usage", "topup", "auto_topup", "refund", "adjustment"]

    key = models.CharField(max_length=255)
    type = models.CharField(max_length=20)
    status = models.CharField(max_length=20, default="complete")
    amount_cents = models.DecimalField(max_digits=14, decimal_places=4)
    real_cost_cents = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    remaining_balance_cents = models.DecimalField(max_digits=14, decimal_places=4)
    stripe_payment_intent_id = models.CharField(max_length=120, blank=True)
    model = models.CharField(max_length=100, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    cache_read_tokens = models.PositiveIntegerField(default=0)
    cache_write_tokens = models.PositiveIntegerField(default=0)
    rate = models.ForeignKey(ModelPricingRate, null=True, on_delete=models.SET_NULL)
    usage_record = models.ForeignKey(
        "agents.UsageRecord", null=True, blank=True, on_delete=models.SET_NULL
    )
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "key"], name="unique_credit_transaction")
        ]
        indexes = [models.Index(fields=["workspace", "created_at"])]
