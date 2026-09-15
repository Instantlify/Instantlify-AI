from django.db import models

from apps.tenants.models import TenantModel


class FunnelEvent(TenantModel):
    """Append-only conversion trail: comment → DM → reply → booked → paid.

    Rows are written by the services that perform each step, never by clients,
    so the numbers on the analytics page are the numbers that actually happened."""

    class Kind(models.TextChoices):
        COMMENT = "comment"
        DM = "dm"
        TRIGGERED = "triggered"
        REPLIED = "replied"
        LINK_CLICK = "link_click"
        HANDOFF = "handoff"
        BOOKED = "booked"
        PAID = "paid"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    provider = models.CharField(max_length=30, blank=True)
    lead_id = models.UUIDField(null=True)
    conversation_id = models.UUIDField(null=True)
    automation_id = models.UUIDField(null=True)
    experiment_id = models.UUIDField(null=True)
    variant = models.CharField(max_length=10, blank=True)
    amount_cents = models.PositiveIntegerField(default=0)
    # Dedupe key for steps that may be re-attempted (e.g. a resent webhook).
    key = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "created_at"]),
            models.Index(fields=["workspace", "automation_id", "kind"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "key"],
                condition=~models.Q(key=""),
                name="unique_funnel_event_key",
            )
        ]


class Experiment(TenantModel):
    """Splits leads that match a control automation's triggers across two variants."""

    name = models.CharField(max_length=100)
    control = models.ForeignKey(
        "automations.Automation", on_delete=models.CASCADE, related_name="experiments_as_control"
    )
    variant = models.ForeignKey(
        "automations.Automation", on_delete=models.CASCADE, related_name="experiments_as_variant"
    )
    # Percentage of matched leads routed to the variant.
    split = models.PositiveSmallIntegerField(default=50)
    goal = models.CharField(max_length=20, default="booked")
    status = models.CharField(max_length=20, default="running")
    winner = models.CharField(max_length=10, blank=True)
    auto_promote = models.BooleanField(default=False)
    min_leads = models.PositiveIntegerField(default=100)
    concluded_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(split__gte=1, split__lte=99), name="experiment_split_range"
            ),
            models.CheckConstraint(
                condition=~models.Q(control=models.F("variant")), name="experiment_distinct_arms"
            ),
            models.UniqueConstraint(
                fields=["control"],
                condition=models.Q(status="running"),
                name="one_running_experiment_per_control",
            ),
        ]
