from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import DailyMetric, SubscriptionSnapshot

current_workspace = ContextVar("platform_metric_workspace", default="")


@contextmanager
def workspace_metrics(workspace):
    token = current_workspace.set(str(workspace))
    try:
        yield
    finally:
        current_workspace.reset(token)


def increment(name):
    # Monitoring failure must never change the result of a provider side effect.
    try:
        with transaction.atomic():
            names = [name]
            if current_workspace.get():
                names.append(name + ":" + current_workspace.get())
            for metric_name in names:
                item, _ = DailyMetric.objects.get_or_create(
                    day=timezone.now().date(), name=metric_name
                )
                DailyMetric.objects.filter(pk=item.pk).update(value=F("value") + 1)
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Platform metric unavailable", extra={"event_code": "ops_metric_unavailable"}
        )


def revenue_metrics():
    today = timezone.now().date()
    latest = SubscriptionSnapshot.objects.order_by("-day").values_list("day", flat=True).first()
    if not latest:
        return {"as_of": None, "mrr": [], "churn": None}
    current = SubscriptionSnapshot.objects.filter(day=latest)
    base = SubscriptionSnapshot.objects.filter(day=today - timedelta(days=30), status="active")
    baseline = set(base.values_list("workspace_id", flat=True))
    canceled = set(
        current.filter(status="canceled", workspace_id__in=baseline).values_list(
            "workspace_id", flat=True
        )
    )
    return {
        "as_of": latest,
        "mrr": list(
            current.filter(status__in=["active", "past_due"])
            .values("currency")
            .annotate(cents=Sum("monthly_cents"))
        ),
        "churn": f"{len(canceled) / len(baseline):.1%}" if baseline else None,
        "overage": list(
            SubscriptionSnapshot.objects.filter(day__gte=today - timedelta(days=30))
            .values("day")
            .annotate(messages=Sum("overage"))
        ),
    }


def monthly_amounts(subscription):
    amounts = defaultdict(Decimal)
    for item in subscription.get("items", {}).get("data", []):
        price = item["price"]
        recurring = price.get("recurring") or {}
        if recurring.get("usage_type") == "metered":
            continue
        unit = price.get("unit_amount_decimal") or price.get("unit_amount")
        if unit is None:
            raise ValueError("unsupported_tiered_price")
        interval = recurring.get("interval")
        factors = {
            "month": Decimal(1),
            "year": Decimal(1) / 12,
            "week": Decimal(52) / 12,
            "day": Decimal(365) / 12,
        }
        factor = factors[interval] / int(recurring.get("interval_count", 1))
        amounts[price["currency"]] += Decimal(str(unit)) * int(item.get("quantity") or 1) * factor
    return amounts
