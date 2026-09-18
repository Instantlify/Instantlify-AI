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


# ============================================================ dashboard metrics
# The console overview (2.5.1). Cheap counts are computed per request; anything that
# scans a large table or calls Stripe is cached for CACHE_SECONDS and labelled with
# the time it was computed, so nobody mistakes a cached figure for a live one.

CACHE_SECONDS = 300


def _cached(key, compute):
    """Returns (value, computed_at). The timestamp travels with the value so the card
    can say "cached at 14:05" instead of implying it is live."""
    from django.core.cache import cache

    hit = cache.get(key)
    if hit is not None:
        return hit
    value = (compute(), timezone.now())
    cache.set(key, value, CACHE_SECONDS)
    return value


def _dollars(cents):
    return (Decimal(cents or 0) / 100).quantize(Decimal("0.01"))


def _monthly_cents(price):
    if not price:
        return Decimal(0)
    if price.billing_interval == "annual":
        return Decimal(price.price_cents) / 12
    return Decimal(price.price_cents)


class PlatformMetricsService:
    """One method per card group. Nothing here returns an invented number: a figure
    with no data source comes back as None and renders as a dash."""

    SOURCES = {"database", "stripe"}
    WINDOWS = {7, 30, 90, 365}

    def __init__(self, *, source="database", days=30, now=None):
        self.source = source if source in self.SOURCES else "database"
        self.days = days if days in self.WINDOWS else 30
        self.now = now or timezone.now()
        self.since = self.now - timedelta(days=self.days)
        self.today = self.now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ------------------------------------------------------------------ hero row

    def revenue(self):
        if self.source == "stripe":
            value, at = _cached(f"ops:revenue:stripe:{self.days}", self._stripe_revenue)
        else:
            value, at = _cached(f"ops:revenue:db:{self.days}", self._database_revenue)
        return {"value": value, "cached_at": at}

    def _stripe_revenue(self):
        """Gross charges settled in Stripe over the window. None when Stripe is not
        configured or unreachable: zero would read as "no revenue", which is a lie."""
        import stripe
        from django.conf import settings

        if not settings.STRIPE_SECRET_KEY:
            return None
        total = 0
        try:
            for item in stripe.BalanceTransaction.list(
                created={"gte": int(self.since.timestamp())},
                limit=100,
                api_key=settings.STRIPE_SECRET_KEY,
            ).auto_paging_iter():
                if item["type"] in {"charge", "payment"}:
                    total += item["amount"]
        except stripe.StripeError:
            return None
        return _dollars(total)

    def _database_revenue(self):
        """Revenue this database has recorded: paid invoices from the Stripe webhook
        ledger plus AI credit purchases."""
        import json

        from apps.billing.models import BillingEvent

        cents = 0
        for event in BillingEvent.all_objects.filter(created_at__gte=self.since).iterator():
            try:
                payload = json.loads(event.payload)
            except (TypeError, ValueError):
                continue
            if payload.get("type") == "invoice.paid":
                invoice = (payload.get("data") or {}).get("object") or {}
                cents += int(invoice.get("amount_paid") or 0)
        return _dollars(cents) + self.credit_revenue()

    def mrr(self):
        from apps.billing.models import BillingAccount

        paying = BillingAccount.all_objects.filter(
            status__in=["active", "past_due"], plan_price__isnull=False
        ).select_related("plan_price")
        count = paying.count()
        latest = SubscriptionSnapshot.objects.order_by("-day").values_list("day", flat=True).first()
        if latest:
            # Snapshots are Stripe's own monthly amounts after discounts; prefer them.
            cents = (
                SubscriptionSnapshot.objects.filter(
                    day=latest, status__in=["active", "past_due"]
                ).aggregate(total=Sum("monthly_cents"))["total"]
                or 0
            )
            basis = f"Stripe snapshot, {latest:%b} {latest.day}"
        else:
            cents = sum((_monthly_cents(account.plan_price) for account in paying), Decimal(0))
            basis = "list prices; no Stripe snapshot yet"
        return {
            "value": _dollars(cents),
            "paying": count,
            "average": _dollars(Decimal(cents) / count) if count else None,
            "basis": basis,
        }

    def trial_mrr(self):
        """What trialing workspaces would pay on conversion. A pipeline figure; the
        template labels it that way so it is never read as revenue."""
        from apps.billing.models import BillingAccount

        rows = {}
        for account in BillingAccount.all_objects.filter(
            status="trialing", plan_price__isnull=False
        ).select_related("plan_price__plan"):
            plan = account.plan_price.plan
            monthly = _monthly_cents(account.plan_price)
            row = rows.setdefault(
                plan.slug, {"name": plan.name, "count": 0, "cents": Decimal(0), "unit": monthly}
            )
            row["count"] += 1
            row["cents"] += monthly
        return [
            {
                "name": row["name"],
                "count": row["count"],
                "total": _dollars(row["cents"]),
                "unit": _dollars(row["unit"]),
            }
            for row in sorted(rows.values(), key=lambda item: -item["cents"])
        ]

    def lifetime_users(self):
        """Accounts on a custom or partner tier. Old tiers are retired with
        is_active=False, never deleted, so their subscribers still count here."""
        from django.db.models import Count

        from apps.billing.models import BillingAccount

        return [
            {
                "name": row["plan_price__plan__partner_label"] or row["plan_price__plan__name"],
                "total": row["total"],
            }
            for row in BillingAccount.all_objects.filter(plan_price__plan__is_custom=True)
            .values("plan_price__plan__name", "plan_price__plan__partner_label")
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        ]

    def credit_revenue(self):
        from apps.billing.models import AICreditTransaction

        cents = AICreditTransaction.all_objects.filter(
            created_at__gte=self.since, type__in=["topup", "auto_topup"], status="complete"
        ).aggregate(total=Sum("amount_cents"))["total"]
        return _dollars(cents)

    # ------------------------------------------------------------- secondary rows

    def users(self):
        from apps.tenants.models import User

        from .models import SignupFunnelEvent

        total = User.objects.count()
        onboarded = (
            SignupFunnelEvent.objects.filter(
                flow="wizard", step="payment", status__in=["completed", "skipped"]
            )
            .values("user_id")
            .distinct()
            .count()
        )
        return {
            "total": total,
            "active": User.objects.filter(last_login__gte=self.since).count(),
            "banned": User.objects.filter(is_banned=True).count(),
            "onboarded": onboarded,
            "onboarded_rate": f"{onboarded * 100 / total:.1f}%" if total else None,
        }

    def tokens(self):
        def compute():
            from apps.agents.models import UsageRecord

            records = UsageRecord.all_objects.all()
            total = records.aggregate(i=Sum("input_tokens"), o=Sum("output_tokens"))
            today = records.filter(created_at__gte=self.today).aggregate(
                i=Sum("input_tokens"), o=Sum("output_tokens")
            )
            return {
                "total": (total["i"] or 0) + (total["o"] or 0),
                "today": (today["i"] or 0) + (today["o"] or 0),
                "requests": records.aggregate(n=Sum("calls"))["n"] or 0,
            }

        value, at = _cached("ops:tokens", compute)
        return {**value, "cached_at": at}

    def contacts(self):
        from apps.crm.models import Lead

        return {
            "total": Lead.all_objects.count(),
            "today": Lead.all_objects.filter(created_at__gte=self.today).count(),
        }

    def landing(self):
        from .models import PageSignup, PageVisit

        visitors = PageVisit.objects.values("session_id").distinct().count()
        signups = PageSignup.objects.count()
        return {
            "visitors": visitors,
            "signups": signups,
            "rate": f"{signups * 100 / visitors:.2f}%" if visitors else None,
        }

    def automations(self):
        from apps.automations.models import Automation, ConversationState

        finished = ConversationState.all_objects.filter(
            created_at__gte=self.since, status__in=["completed", "failed"]
        )
        done = finished.count()
        return {
            "total": Automation.all_objects.count(),
            "active": Automation.all_objects.filter(enabled=True).count(),
            "success": (
                f"{finished.filter(status='completed').count() * 100 / done:.0f}%" if done else None
            ),
        }

    def messages(self):
        def compute():
            from apps.crm.models import Message

            month = self.today.replace(day=1)
            sent = Message.all_objects.filter(direction="outbound")
            return {"total": sent.count(), "month": sent.filter(created_at__gte=month).count()}

        value, at = _cached("ops:messages", compute)
        return {**value, "cached_at": at}

    def connections(self):
        from django.db.models import Count

        from apps.channels.models import ChannelConnection

        counts = dict(
            ChannelConnection.all_objects.exclude(status="disconnected")
            .values_list("provider")
            .annotate(total=Count("id"))
        )
        return [
            {"provider": provider, "total": counts.get(provider, 0)}
            for provider in ["instagram", "whatsapp", "telegram", "messenger"]
        ]

    def integrations(self):
        from django.db.models import Count

        from apps.crm.models import IntegrationConfig

        live = IntegrationConfig.all_objects.exclude(status="disconnected")
        top = live.values("provider").annotate(total=Count("id")).order_by("-total").first()
        return {"total": live.count(), "top": top}

    def teams(self):
        from django.db.models import Count

        from apps.tenants.models import Membership

        sizes = list(
            Membership.all_objects.values("workspace_id")
            .annotate(members=Count("id"))
            .values_list("members", flat=True)
        )
        return {
            "multi": sum(1 for size in sizes if size > 1),
            "solo": sum(1 for size in sizes if size == 1),
            "average": f"{sum(sizes) / len(sizes):.2f}" if sizes else None,
        }

    def mcp(self):
        """MCP clients (Claude Desktop, Claude Code, agents) seen in the window. A client
        counts once per API key; `last_active_at` moves on every request it makes."""
        from apps.public_api.models import MCPClient

        active = MCPClient.all_objects.filter(last_active_at__gte=self.since)
        return {
            "clients": active.count(),
            "workspaces": active.values("workspace_id").distinct().count(),
        }

    def billing_locks(self):
        """Workspaces whose subscription is past due or unpaid, valued at their plan's
        monthly price: what is owed and not collected."""
        from apps.billing.models import BillingAccount

        locked = list(
            BillingAccount.all_objects.filter(status__in=["past_due", "unpaid"]).select_related(
                "plan_price"
            )
        )
        return {
            "owed": _dollars(sum((_monthly_cents(a.plan_price) for a in locked), Decimal(0))),
            "count": len(locked),
        }

    # ------------------------------------------------------------------- charts

    def charts(self):
        value, at = _cached(f"ops:charts:{self.days}", self._charts)
        return {**value, "cached_at": at}

    def _charts(self):
        from . import charts

        unit = charts.granularity(self.days)
        start = timezone.localtime(self.since).date()
        end = timezone.localtime(self.now).date()
        slots = charts.buckets(start, end, unit)
        return {
            "unit": unit,
            "signups": charts.line_chart(
                [(charts.label(day, unit), count) for day, count in self._signups(slots, unit)]
            ),
            "subscriptions": charts.bar_chart(
                [
                    (charts.label(day, unit), new, lost)
                    for day, new, lost in self._subscription_changes(slots, unit)
                ]
            ),
            "tiers": charts.donut(self._tiers()),
            "mrr": charts.line_chart(self._mrr_history(), money=True),
        }

    def _signups(self, slots, unit):
        from django.db.models import Count, DateField
        from django.db.models.functions import TruncDate, TruncMonth, TruncWeek

        from apps.tenants.models import User

        trunc = {"day": TruncDate, "week": TruncWeek, "month": TruncMonth}[unit]
        counts = dict(
            User.objects.filter(date_joined__gte=self.since)
            .annotate(bucket=trunc("date_joined", output_field=DateField()))
            .values_list("bucket")
            .annotate(total=Count("id"))
        )
        return [(day, counts.get(day, 0)) for day in slots]

    def _subscription_changes(self, slots, unit):
        """New and ended subscriptions from the Stripe webhook ledger, dated by when
        Stripe says the event happened rather than when we happened to receive it."""
        import json
        from datetime import datetime

        from apps.billing.models import BillingEvent

        from .charts import bucket_of

        new, lost = defaultdict(int), defaultdict(int)
        for event in BillingEvent.all_objects.filter(created_at__gte=self.since).iterator():
            try:
                payload = json.loads(event.payload)
            except (TypeError, ValueError):
                continue
            kind = payload.get("type")
            if kind not in {"customer.subscription.created", "customer.subscription.deleted"}:
                continue
            when = (
                timezone.localtime(
                    datetime.fromtimestamp(
                        int(payload["created"]), tz=timezone.get_current_timezone()
                    )
                ).date()
                if payload.get("created")
                else timezone.localtime(event.created_at).date()
            )
            target = new if kind.endswith("created") else lost
            target[bucket_of(when, unit)] += 1
        return [(day, new[day], lost[day]) for day in slots]

    def _tiers(self):
        """Workspaces per plan today. Accounts with no plan price are on the default
        (free) plan; ended subscriptions are left out."""
        from django.conf import settings
        from django.db.models import Count

        from apps.billing.models import BillingAccount, Plan

        default = (
            Plan.objects.filter(slug=settings.DEFAULT_PLAN_SLUG)
            .values_list("name", flat=True)
            .first()
            or settings.DEFAULT_PLAN_SLUG.title()
        )
        rows = (
            BillingAccount.all_objects.exclude(status__in=["canceled", "incomplete_expired"])
            .values("plan_price__plan__name", "plan_price__plan__partner_label")
            .annotate(total=Count("id"))
        )
        merged = defaultdict(int)
        for row in rows:
            name = (
                row["plan_price__plan__partner_label"] or row["plan_price__plan__name"] or default
            )
            merged[name] += row["total"]
        return sorted(merged.items(), key=lambda item: -item[1])

    def _mrr_history(self):
        """Month-end MRR for the last twelve months, from the nightly Stripe snapshots.
        Each month uses its latest snapshot day, so a partial month shows where it is now."""
        from django.db.models import Q

        first = (self.today.date().replace(day=1) - timedelta(days=335)).replace(day=1)
        days = dict(
            SubscriptionSnapshot.objects.filter(day__gte=first)
            .values_list("day")
            .annotate(cents=Sum("monthly_cents", filter=Q(status__in=["active", "past_due"])))
        )
        month_end = {}
        for day in sorted(days):
            month_end[day.replace(day=1)] = days[day] or 0
        return [(f"{month:%b %Y}", _dollars(cents)) for month, cents in sorted(month_end.items())]

    def snapshot(self):
        return {
            "charts": self.charts(),
            "source": self.source,
            "days": self.days,
            "revenue": self.revenue(),
            "mrr": self.mrr(),
            "trial_mrr": self.trial_mrr(),
            "lifetime": self.lifetime_users(),
            "credit_revenue": self.credit_revenue(),
            "users": self.users(),
            "tokens": self.tokens(),
            "contacts": self.contacts(),
            "landing": self.landing(),
            "automations": self.automations(),
            "messages": self.messages(),
            "connections": self.connections(),
            "integrations": self.integrations(),
            "teams": self.teams(),
            "locks": self.billing_locks(),
            "mcp": self.mcp(),
        }
