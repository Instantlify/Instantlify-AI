import hashlib
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.utils import timezone

from apps.automations.models import Automation
from apps.tenants.services import audit

from .models import Experiment, FunnelEvent


def record(workspace_id, kind, *, key="", **fields):
    """Append a funnel event; a repeated key is a no-op so callers stay idempotent."""
    try:
        with transaction.atomic():
            return FunnelEvent.objects.for_workspace(workspace_id).create(
                workspace_id=workspace_id, kind=kind, key=key, **fields
            )
    except IntegrityError:
        return None


def attribution(conversation):
    """Automation/experiment/variant that most recently engaged this conversation."""
    from apps.automations.models import ConversationState

    state = (
        ConversationState.objects.for_workspace(conversation.workspace_id)
        .filter(conversation=conversation)
        .only("automation_id", "experiment_id", "variant")
        .first()
    )
    if not state:
        return {}
    return {
        "automation_id": state.automation_id,
        "experiment_id": state.experiment_id,
        "variant": state.variant,
    }


def assign_arm(experiment, lead_id):
    """Deterministic per-lead bucket: the same lead always sees the same variant."""
    digest = hashlib.sha256(f"{experiment.pk}:{lead_id}".encode()).digest()
    bucket = int.from_bytes(digest[:2], "big") % 100
    return "variant" if bucket < experiment.split else "control"


def choose_automation(trigger_automation, lead_id):
    experiment = (
        Experiment.objects.for_workspace(trigger_automation.workspace_id)
        .filter(control=trigger_automation, status="running")
        .select_related("variant")
        .first()
    )
    if not experiment or not experiment.variant.enabled or not experiment.variant.published:
        return trigger_automation, None, ""
    arm = assign_arm(experiment, lead_id)
    return (experiment.variant if arm == "variant" else experiment.control), experiment, arm


PERIODS = {"7d": 7, "30d": 30, "90d": 90}
STEPS = ["comment", "dm", "triggered", "replied", "booked", "paid"]


def funnel(workspace_id, *, period="30d", automation_id=None, provider=""):
    since = timezone.now() - timedelta(days=PERIODS.get(period, 30))
    events = FunnelEvent.objects.for_workspace(workspace_id).filter(created_at__gte=since)
    if automation_id:
        events = events.filter(automation_id=automation_id)
    if provider:
        events = events.filter(provider=provider)
    counts = {
        row["kind"]: row["leads"]
        for row in events.exclude(lead_id=None)
        .values("kind")
        .annotate(leads=Count("lead_id", distinct=True))
    }
    revenue = events.filter(kind="paid").aggregate(total=Sum("amount_cents"))["total"] or 0
    steps = [{"kind": kind, "leads": counts.get(kind, 0)} for kind in STEPS]
    unique_leads = (
        events.filter(kind__in=["comment", "dm"])
        .exclude(lead_id=None)
        .values("lead_id")
        .distinct()
        .count()
    )
    for step in steps:
        # Comments and DMs are alternative entry points, not sequential stages.
        previous_kinds = {
            "triggered": ["comment", "dm"],
            "replied": ["triggered"],
            "booked": ["replied"],
            "paid": ["booked"],
        }.get(step["kind"])
        step["conversion"] = None
        if previous_kinds:
            previous = events.filter(kind__in=previous_kinds).exclude(lead_id=None)
            denominator = previous.values("lead_id").distinct().count()
            earlier = previous.filter(
                lead_id=OuterRef("lead_id"), created_at__lte=OuterRef("created_at")
            )
            converted = (
                events.filter(kind=step["kind"])
                .filter(Exists(earlier))
                .values("lead_id")
                .distinct()
                .count()
            )
            step["conversion"] = round(converted / denominator, 4) if denominator else None
    by_automation = list(
        events.exclude(automation_id=None)
        .values("automation_id")
        .annotate(
            triggered=Count("lead_id", distinct=True, filter=Q(kind="triggered")),
            booked=Count("lead_id", distinct=True, filter=Q(kind="booked")),
            paid=Count("lead_id", distinct=True, filter=Q(kind="paid")),
            revenue_cents=Sum("amount_cents", filter=Q(kind="paid")),
        )
        .order_by("-triggered")[:50]
    )
    names = dict(
        Automation.objects.for_workspace(workspace_id)
        .filter(pk__in=[row["automation_id"] for row in by_automation])
        .values_list("id", "name")
    )
    for row in by_automation:
        row["name"] = names.get(row["automation_id"], "Deleted automation")
        row["revenue_cents"] = row["revenue_cents"] or 0
    by_channel = list(
        events.exclude(provider="")
        .values("provider")
        .annotate(
            leads=Count("lead_id", distinct=True),
            booked=Count("lead_id", distinct=True, filter=Q(kind="booked")),
            paid=Count("lead_id", distinct=True, filter=Q(kind="paid")),
        )
        .order_by("-leads")
    )
    return {
        "period": period,
        "since": since,
        "steps": steps,
        "unique_leads": unique_leads,
        "revenue_cents": revenue,
        "automations": by_automation,
        "channels": by_channel,
    }


def experiment_results(experiment):
    events = FunnelEvent.objects.for_workspace(experiment.workspace_id).filter(
        experiment_id=experiment.pk
    )
    arms = {}
    for arm in ["control", "variant"]:
        scoped = events.filter(variant=arm)
        leads = scoped.filter(kind="triggered").values("lead_id").distinct().count()
        goals = scoped.filter(kind=experiment.goal).values("lead_id").distinct().count()
        arms[arm] = {
            "leads": leads,
            "conversions": goals,
            "rate": round(goals / leads, 4) if leads else 0.0,
        }
    return arms


@transaction.atomic
def promote(experiment, winner, actor=None):
    if winner not in {"control", "variant"}:
        raise ValueError("invalid_winner")
    experiment = (
        Experiment.objects.for_workspace(experiment.workspace_id)
        .select_for_update()
        .get(pk=experiment.pk)
    )
    if experiment.status != "running":
        return experiment
    if winner == "variant":
        # The winning graph is republished under the control automation, so the
        # automation everyone links to keeps its ID; the variant copy is retired.
        _swap_graph(experiment.control, experiment.variant, actor)
    else:
        Automation.objects.for_workspace(experiment.workspace_id).filter(
            pk=experiment.variant_id
        ).update(enabled=False)
    experiment.status = "concluded"
    experiment.winner = winner
    experiment.concluded_at = timezone.now()
    experiment.save()
    audit(experiment.workspace, actor, "experiment.concluded", experiment.id)
    return experiment


def _swap_graph(control, variant, actor):
    from apps.automations.services import publish

    publish(control, variant.published, actor)
    Automation.objects.for_workspace(variant.workspace_id).filter(pk=variant.pk).update(
        enabled=False
    )


def maybe_auto_promote(experiment):
    if not experiment.auto_promote or experiment.status != "running":
        return
    arms = experiment_results(experiment)
    if min(arm["leads"] for arm in arms.values()) < experiment.min_leads:
        return
    control, variant = arms["control"]["rate"], arms["variant"]["rate"]
    if variant == control:
        return
    promote(experiment, "variant" if variant > control else "control")
