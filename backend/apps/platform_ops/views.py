import hashlib
import secrets
import time
import uuid
from datetime import timedelta
from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.tenants.client_ip import client_ip
from apps.tenants.models import Workspace

from .models import (
    Control,
    OperationStatus,
    PlatformAudit,
    PlatformInvite,
    PlatformRole,
    PlatformSetting,
    SupportSession,
)
from .security import new_secret, record, verify_otp

# Dashboard sections. Each renders alone; the sidebar switches between them.
TABS = [
    "overview",
    "funnel",
    "website_stats",
    "ai_credits",
    "users",
    "workspaces",
    "segments",
    "tiers",
    "automations",
    "blog",
    "support",
    "agent_config",
    "revenue",
    "billing_audit",
    "promo_offers",
    "notifications",
    "email_templates",
    "settings",
    "operations",
    "controls",
    "team",
    "audit",
]


def short_date(value, *, with_year=False, with_time=False):
    """`Sep 7` / `Sep 7, 2026` / `Sep 7, 1:58 PM`, without platform-specific strftime
    directives — `%-d` is glibc-only and raises on Windows."""
    if not value:
        return ""
    text = f"{value.strftime('%b')} {value.day}"
    if with_year:
        text += f", {value.year}"
    if with_time:
        hour = value.hour % 12 or 12
        text += f", {hour}:{value.strftime('%M %p')}"
    return text


def short_weekday(value):
    return f"{value.strftime('%a')}, {value.strftime('%b')} {value.day}" if value else ""


def funnel_dataset():
    """Both signup funnels, from the events the wizard and the product tour write.

    Counted by distinct user, so one person refreshing a step never looks like
    traffic, and a teammate riding an owner's subscription is separated out rather
    than inflating the signup count.
    """
    from apps.tenants.models import User

    from .growth import funnel_report
    from .models import SignupFunnelEvent

    wizard = funnel_report("wizard")
    tour = funnel_report("tour")
    shades = ["#4F46E5", "#0284C7", "#10B981", "#7C3AED", "#F59E0B"]
    for index, step in enumerate(wizard["steps"]):
        step["color"] = shades[index % len(shades)]
    paywall = next(
        (step for step in wizard["steps"] if step["name"] == "payment"),
        {"reached": 0, "completed": 0},
    )
    signups = User.objects.count()
    worst = wizard["worst"]
    reached_names = {step["name"]: step for step in wizard["steps"]}
    people = (
        SignupFunnelEvent.objects.select_related("user")
        .filter(flow="tour")
        .order_by("-created_at")[:25]
    )
    return {
        "total_signups": signups,
        "reached_paywall": paywall["reached"],
        "saw_paywall_never_converted": max(0, paywall["reached"] - paywall["completed"]),
        "converted_to_paid": paywall["completed"],
        "conversion_rate": (f"{paywall['completed'] * 100 / signups:.1f}%" if signups else "0.0%"),
        "steps": wizard["steps"],
        "dropoff_highlight": (
            f"Biggest drop-off: {worst['drop_off']} of people who reached "
            f"{previous_step(wizard['steps'], worst['name'])} never reached {worst['name']}."
            if worst
            else "No drop-off recorded yet."
        ),
        "tour_steps": [{**step, "pct": step["reached"]} for step in tour["steps"]],
        "users": [
            {
                "email": getattr(event.user, "email", "—"),
                "step": f"{event.step} ({event.status})",
                "time": short_date(event.created_at, with_time=True),
                "role": "Account owner" if event.is_owner else "Teammate",
            }
            for event in people
        ],
        "empty": not reached_names or not any(step["reached"] for step in wizard["steps"]),
    }


def previous_step(steps, name):
    names = [step["name"] for step in steps]
    index = names.index(name) if name in names else 0
    return names[index - 1] if index else name


def analytics_dataset():
    """Signups, subscriptions vs churn, tier mix and MRR growth — all from this
    database. Charts are drawn from these points, so a flat line here means a flat
    month, not a broken query."""
    from django.db.models.functions import TruncDate

    from apps.billing.models import BillingAccount
    from apps.tenants.models import User

    from .models import SubscriptionSnapshot

    today = timezone.now().date()
    days = [today - timedelta(days=offset) for offset in range(29, -1, -1)]
    signups = dict(
        User.objects.filter(date_joined__date__gte=days[0])
        .annotate(day=TruncDate("date_joined"))
        .values("day")
        .annotate(total=Count("id"))
        .values_list("day", "total")
    )
    started = dict(
        BillingAccount.all_objects.filter(created_at__date__gte=days[0])
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .values_list("day", "total")
    )
    # A cancelled subscription churns when its paid period actually ends, not when
    # the row was last touched.
    churned = dict(
        BillingAccount.all_objects.filter(status="canceled", period_end__date__gte=days[0])
        .annotate(day=TruncDate("period_end"))
        .values("day")
        .annotate(total=Count("id"))
        .values_list("day", "total")
    )
    tiers = (
        BillingAccount.all_objects.values("plan_price__plan__name")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )
    total_accounts = sum(row["total"] for row in tiers) or 1
    shades = [
        "#4F46E5",
        "#0284C7",
        "#10B981",
        "#7C3AED",
        "#EA580C",
        "#0D9488",
        "#D97706",
        "#0891B2",
        "#8B5CF6",
        "#E11D48",
    ]
    months = (
        SubscriptionSnapshot.objects.filter(day__gte=today - timedelta(days=210))
        .values("day")
        .annotate(total=Sum("monthly_cents"))
        .order_by("day")[:7]
    )
    points, peak = [], max([row["total"] or 0 for row in months] or [0]) or 1
    for index, row in enumerate(months):
        value = float(row["total"] or 0) / 100
        points.append(
            {
                "month": row["day"].strftime("%b %y"),
                "val": round(value),
                "x": 30 + index * 70,
                "y": round(150 - (value / (float(peak) / 100) * 130)) if peak else 150,
            }
        )
    return {
        "user_signups": [
            {
                "date": short_date(day),
                "day": short_weekday(day),
                "val": signups.get(day, 0),
            }
            for day in days[::2]
        ],
        "subs_churn": [
            {
                "date": short_date(day),
                "churn": churned.get(day, 0),
                "subs": started.get(day, 0),
            }
            for day in days[::2]
        ],
        "tier_slices": [
            {
                "label": row["plan_price__plan__name"] or "Free",
                "pct": round(row["total"] * 100 / total_accounts),
                "color": shades[index % len(shades)],
            }
            for index, row in enumerate(tiers)
        ],
        "mrr_points": points,
    }


# ------------------------------------------------------- module data (all live)


def website_stats_dataset(first_touch=False):
    """First-party marketing-site analytics. Separate from product analytics: this
    counts logged-out visitors on public pages."""
    from .growth import page_stats, source_breakdown
    from .models import PageSignup, PageVisit

    pages = list(PageVisit.objects.values_list("page", flat=True).distinct()[:6])
    visitors = PageVisit.objects.values("session_id").distinct().count()
    signups = PageSignup.objects.count()
    return {
        "pages": [page_stats(page, first_touch=first_touch) for page in pages],
        "first_touch": first_touch,
        "overall": {
            "visitors": visitors,
            "signups": signups,
            "conversion": f"{signups * 100 / visitors:.1f}%" if visitors else "0.0%",
        },
        "overall_sources": source_breakdown(PageVisit.objects.all(), first_touch=first_touch),
        "first_touch_sources": source_breakdown(PageVisit.objects.all(), first_touch=True),
        "empty": not pages,
    }


def segments_dataset():
    """Marketing categories derived from each connected account's public profile.
    Category share counts primary accounts only; the multi-category tab counts every
    connected account, which is how an agency shows up as one."""
    from django.db.models import Count

    from .models import SegmentCategory, UserSegment

    primary = UserSegment.objects.filter(is_primary=True)
    ranked = list(primary.values("category").annotate(total=Count("id")).order_by("-total")[:15])
    total = sum(row["total"] for row in ranked) or 1
    widest = ranked[0]["total"] if ranked else 1
    categorized = primary.values("user_id").distinct().count()
    multi = (
        UserSegment.objects.values("user_id", "user__email")
        .annotate(categories=Count("category", distinct=True), accounts=Count("id"))
        .filter(categories__gt=1)
        .order_by("-accounts")[:25]
    )
    rows = []
    for row in multi:
        tags = sorted(
            set(
                UserSegment.objects.filter(user_id=row["user_id"]).values_list(
                    "category", flat=True
                )
            )
        )
        rows.append({"email": row["user__email"], "accounts": row["accounts"], "tags": tags})
    return {
        "categorized": categorized,
        "insufficient": unclassified_accounts(),
        "uncategorized": pending_accounts(),
        "multi_category": len(rows),
        "categories": [
            {
                "name": row["category"],
                "count": row["total"],
                "pct": round(row["total"] * 100 / total, 1),
                "width": round(row["total"] * 100 / widest),
            }
            for row in ranked
        ],
        "multi": rows,
        "label_set": list(SegmentCategory.objects.filter(is_active=True)),
        "empty": not ranked,
    }


def unclassified_accounts():
    """Accounts the classifier looked at and could not place. A thin bio genuinely
    does not say what a business does; a forced guess would pollute every count."""
    from apps.channels.models import ChannelConnection

    from .models import UserSegment

    classified = set(UserSegment.objects.values_list("source_account", flat=True))
    return (
        ChannelConnection.all_objects.exclude(profile={})
        .exclude(display_name__in=classified)
        .count()
    )


def pending_accounts():
    from apps.channels.models import ChannelConnection

    return ChannelConnection.all_objects.filter(profile={}).count()


def blog_dataset(days=90, editing=""):
    from .growth import blog_analytics
    from .models import BlogCategory, BlogPost

    posts = BlogPost.objects.select_related("category")[:100]
    return {
        "posts": [
            {
                "id": post.pk,
                "title": post.title,
                "slug": post.slug,
                "date": short_date(post.published_at or post.created_at, with_year=True),
                "status": post.status,
                "category": post.category.name if post.category else "—",
            }
            for post in posts
        ],
        "categories": list(BlogCategory.objects.all()),
        "analytics": blog_analytics(days if days in {7, 30, 90} else 90),
        "editing": (
            BlogPost.objects.select_related("category").filter(pk=editing).first()
            if str(editing).isdigit()
            else None
        ),
        "empty": not posts,
    }


def support_tickets_dataset(queue="billing"):
    from .growth import ticket_counts
    from .models import PlatformRole, SupportTicket

    counts = ticket_counts()
    tickets = (
        SupportTicket.objects.filter(category=queue)
        .select_related("assignee", "workspace")
        .prefetch_related("messages")[:100]
    )
    return {
        "total": SupportTicket.objects.count(),
        "unread": SupportTicket.objects.filter(is_read=False).count(),
        "counts": counts,
        "queue": queue,
        "staff": list(
            PlatformRole.objects.select_related("user").filter(
                active=True, user__is_active=True, role__in=["owner", "support"]
            )
        ),
        "tickets": [
            {
                "id": ticket.pk,
                "ref": ticket.ticket_number,
                "who": ticket.reporter_name or "—",
                "subject": ticket.subject,
                "body": ticket.body,
                "messages": ticket.messages.all(),
                "email": ticket.reporter_email,
                "age": ticket.created_at,
                "assignee": ticket.assignee.get_username() if ticket.assignee else "Unassigned",
                "assignee_id": getattr(ticket.assignee, "pk", ""),
                "status": "Resolved" if ticket.status == "resolved" else "Not resolved",
                "resolved": ticket.status == "resolved",
                "kind": ticket.category,
                "unread": not ticket.is_read,
                "by_agent": ticket.opened_by_agent,
            }
            for ticket in tickets
        ],
        "empty": not tickets,
    }


def notifications_dataset(kind="", editing=""):
    from zoneinfo import ZoneInfo

    from django.utils import timezone

    from .models import Announcement

    rows = Announcement.objects.prefetch_related("target_plans", "views")
    if kind in {"popup", "strip"}:
        rows = rows.filter(type=kind)
    items = []
    for item in rows[:100]:
        plans = [plan.name for plan in item.target_plans.all()]
        pages = item.pages()
        items.append(
            {
                "id": item.pk,
                "type": item.type.title(),
                "name": item.name,
                "created": item.created_at,
                "preview": item.title or item.body[:120],
                "reads": len(
                    set(item.views.values_list("user_id", flat=True))
                    | set(
                        item.notifications.filter(read_at__isnull=False).values_list(
                            "user_id", flat=True
                        )
                    )
                ),
                "acknowledged": item.notifications.filter(acknowledged_at__isnull=False)
                .values("user_id")
                .distinct()
                .count(),
                "schedule": (
                    "Draft"
                    if not item.is_active
                    else "Scheduled"
                    if item.starts_at and item.starts_at > timezone.now()
                    else "Expired"
                    if item.ends_at and item.ends_at <= timezone.now()
                    else "Live"
                    if item.is_active
                    else "Draft"
                ),
                "starts_at": item.starts_at,
                "ends_at": item.ends_at,
                "targeting": " · ".join(
                    [
                        "Pages: " + (", ".join(pages) if pages else "all pages"),
                        "Tiers: " + (", ".join(plans) if plans else "all tiers"),
                    ]
                ),
                "tone": item.tone,
                "active": item.is_active,
            }
        )
    everything = Announcement.objects.all()
    editing_item = (
        Announcement.objects.prefetch_related("target_plans").filter(pk=editing).first()
        if str(editing).isdigit()
        else None
    )
    if editing_item:
        zone = ZoneInfo(editing_item.schedule_timezone)
        editing_item.start_input = (
            editing_item.starts_at.astimezone(zone).strftime("%Y-%m-%dT%H:%M")
            if editing_item.starts_at
            else ""
        )
        editing_item.end_input = (
            editing_item.ends_at.astimezone(zone).strftime("%Y-%m-%dT%H:%M")
            if editing_item.ends_at
            else ""
        )
    return {
        "total": everything.count(),
        "active": everything.filter(is_active=True).count(),
        "reads": sum(item["reads"] for item in items),
        "popups": everything.filter(type="popup").count(),
        "strips": everything.filter(type="strip").count(),
        "items": items,
        "filter": kind,
        "editing": editing_item,
        "empty": not items,
    }


def email_templates_dataset():
    from .models import EmailTemplate

    return [
        {
            "id": template.pk,
            "name": template.name,
            "note": template.description,
            "subject": template.subject,
            "body": template.body,
            "updated": template.updated_at,
            "status": template.status,
            "active": template.status == "active",
        }
        for template in EmailTemplate.objects.all()
    ]


def billing_audit_context():
    from .models import BillingAuditRun

    run = BillingAuditRun.objects.first()
    findings = (run.findings if run else {}) or {}
    return {
        "run": run,
        "stale": findings.get("stale", []),
        "cardless": findings.get("cardless", []),
    }


# ---------------------------------------------------------------- live module queries


def credit_provider_health():
    """One card per platform key in the environment, each with its last on-demand
    test result. Nothing is called here: rendering the page never spends money."""
    from django.core.cache import cache

    from .intelligence import provider_keys

    cards = []
    for key in provider_keys():
        cards.append({**key, "result": cache.get(f"ops:provider-test:{key['env']}")})
    return cards


RATE_UNITS = {
    "m": ("per 1M tokens", 1),
    "token": ("per token", 1_000_000),
    # Roughly four characters per token, so 100 characters is about 25 tokens.
    "chars": ("per 100 chars", 40_000),
}


def in_unit(cents_per_million, unit):
    """A stored rate (cents per million tokens) expressed in dollars per chosen unit.
    Display only: rates are always edited and stored per million tokens."""
    from decimal import Decimal

    divisor = RATE_UNITS.get(unit, RATE_UNITS["m"])[1]
    return Decimal(cents_per_million) / 100 / divisor


def ledger_page(ledger, *, query="", kind="", page=1):
    """Search by workspace name, description or payment intent; filter by type."""
    from django.core.paginator import Paginator

    from apps.billing.models import AICreditTransaction

    rows = ledger.select_related("workspace").order_by("-created_at", "-id")
    if kind in AICreditTransaction.TYPES:
        rows = rows.filter(type=kind)
    if query:
        rows = rows.filter(
            Q(workspace__name__icontains=query)
            | Q(description__icontains=query)
            | Q(stripe_payment_intent_id__icontains=query)
            | Q(model__icontains=query)
        )
    page_obj = Paginator(rows, 50).get_page(page)
    return {
        "page": page_obj,
        "rows": [
            {
                "row": row,
                "amount": row.amount_cents / 100,
                "real_cost": row.real_cost_cents / 100,
                "remaining": row.remaining_balance_cents / 100,
                "tokens": row.tokens_in + row.tokens_out,
            }
            for row in page_obj
        ],
        "query": query,
        "kind": kind,
        "types": AICreditTransaction.TYPES,
    }


def ai_credit_context(start, *, query="", kind="", page=1, unit="m"):
    """Revenue, consumption, balances, per-model usage and the rate card, all read from
    the credit ledger so the console and an invoice can never disagree."""
    from decimal import Decimal

    from django.db.models import Avg

    from apps.billing.models import AICreditBalance, AICreditTransaction, ModelPricingRate

    ledger = AICreditTransaction.all_objects.filter(created_at__gte=start)
    purchases = ledger.filter(type__in=["topup", "auto_topup"], status="complete")
    usage = ledger.filter(type="usage")
    balances = AICreditBalance.all_objects.all()
    buckets = [
        ("0 credits", balances.filter(balance_cents__lte=0).count()),
        ("1 - 10,000", balances.filter(balance_cents__gt=0, balance_cents__lte=10000).count()),
        (
            "10,001 - 50,000",
            balances.filter(balance_cents__gt=10000, balance_cents__lte=50000).count(),
        ),
        (
            "50,001 - 150,000",
            balances.filter(balance_cents__gt=50000, balance_cents__lte=150000).count(),
        ),
        ("150,000+", balances.filter(balance_cents__gt=150000).count()),
    ]
    widest = max([count for _, count in buckets] or [0]) or 1
    models = []
    for row in (
        usage.exclude(model="")
        .values("model")
        .annotate(
            charged=Sum("amount_cents"),
            real=Sum("real_cost_cents"),
            runs=Count("id"),
            tokens_in=Sum("tokens_in"),
            tokens_out=Sum("tokens_out"),
        )
        .order_by("charged")
    ):
        charged = abs(row["charged"] or Decimal(0))
        real = abs(row["real"] or Decimal(0))
        models.append(
            {
                "model": row["model"],
                "runs": row["runs"],
                "tokens": (row["tokens_in"] or 0) + (row["tokens_out"] or 0),
                "charged": charged / 100,
                "real": real / 100,
                "margin": round(float(charged / real), 1) if real else None,
            }
        )
    auto_on = balances.filter(auto_topup_enabled=True)
    return {
        "purchase_revenue": (purchases.aggregate(t=Sum("amount_cents"))["t"] or Decimal(0)) / 100,
        "consumed": abs(usage.aggregate(t=Sum("amount_cents"))["t"] or Decimal(0)) / 100,
        "unique_buyers": purchases.values("workspace_id").distinct().count(),
        "workspace_count": balances.count(),
        "auto_topup_on": auto_on.count(),
        "auto_topup_off": balances.filter(auto_topup_enabled=False).count(),
        "auto_threshold": (auto_on.aggregate(v=Avg("auto_topup_threshold_cents"))["v"] or 0) / 100,
        "auto_amount": (auto_on.aggregate(v=Avg("auto_topup_amount_cents"))["v"] or 0) / 100,
        "total_balance": (balances.aggregate(t=Sum("balance_cents"))["t"] or Decimal(0)) / 100,
        "balance_buckets": [
            {"label": label, "count": count, "pct": round(count * 100 / widest)}
            for label, count in buckets
        ],
        "ledger": ledger_page(ledger, query=query, kind=kind, page=page),
        "transactions": [
            {
                "row": row,
                "amount": row.amount_cents / 100,
                "real_cost": row.real_cost_cents / 100,
                "remaining": row.remaining_balance_cents / 100,
                "tokens": row.tokens_in + row.tokens_out,
            }
            for row in ledger.select_related("workspace").order_by("-created_at")[:25]
        ],
        "models": models,
        "buyers": [
            {
                "name": row["workspace__name"],
                "total": (row["total"] or Decimal(0)) / 100,
                "purchases": row["purchases"],
            }
            for row in purchases.values("workspace__name", "workspace_id")
            .annotate(total=Sum("amount_cents"), purchases=Count("id"))
            .order_by("-total")[:8]
        ],
        # Rates are stored in cents per million tokens; the card shows dollars per million.
        "rates": [
            {
                "rate": rate,
                "margin": rate.margin(),
                "rows": [
                    {
                        "label": label,
                        "field": field,
                        "ours": getattr(rate, "our_" + field) / 100,
                        "real": getattr(rate, "real_" + field) / 100,
                        "ours_shown": in_unit(getattr(rate, "our_" + field), unit),
                        "real_shown": in_unit(getattr(rate, "real_" + field), unit),
                        "margin": (
                            round(
                                float(
                                    getattr(rate, "our_" + field) / getattr(rate, "real_" + field)
                                ),
                                1,
                            )
                            if getattr(rate, "real_" + field)
                            else None
                        ),
                    }
                    for label, field in [
                        ("Input", "input"),
                        ("Output", "output"),
                        ("Cache read", "cache_read"),
                        ("Cache write", "cache_write"),
                    ]
                ],
            }
            for rate in ModelPricingRate.objects.all()
        ],
        "providers": credit_provider_health(),
    }


def automation_runs(automation_id, limit=50):
    """Execution log for one automation: each run's state, how far it got, and why it
    stopped. The first place to look when a client says "my automation isn't working"."""
    from apps.automations.models import Automation, ConversationState

    automation = Automation.all_objects.filter(pk=automation_id).first()
    if not automation:
        return None
    return {
        "automation": automation,
        "runs": ConversationState.all_objects.filter(automation=automation)
        .select_related("conversation")
        .order_by("-created_at")[:limit],
    }


def automation_accounts():
    """Automations grouped by the connected channel that owns them, matching how an
    operator looks for them: find the account first, then read its automations."""
    from apps.automations.models import Automation
    from apps.channels.models import ChannelConnection

    rows = []
    for connection in ChannelConnection.all_objects.select_related("workspace").order_by(
        "workspace__name", "provider"
    )[:60]:
        automations = Automation.all_objects.filter(workspace_id=connection.workspace_id)
        rows.append(
            {
                "connection": connection,
                "workspace": connection.workspace,
                "count": automations.count(),
                "automations": automations[:25],
            }
        )
    return rows


def agent_config_context(selected=""):
    """Instantlify's OWN support bot: its knowledge base and system prompt.

    Deliberately not the tenant agent from `apps.agents`. That one answers a tenant's
    leads about a tenant's business; this one answers our prospects about Instantlify, and
    the two knowledge bases must never retrieve into each other's context.
    """
    from .knowledge_indexing import status
    from .models import PlatformKnowledgeDocument, PlatformKnowledgeSection
    from .support_agent import DEFAULT_PROMPT, system_prompt

    documents = list(PlatformKnowledgeDocument.objects.prefetch_related("sections"))
    current = None
    if selected and selected != "prompt":
        current = next((doc for doc in documents if str(doc.pk) == selected), None)
    current = current or (documents[0] if documents else None)
    total = PlatformKnowledgeSection.objects.count()
    return {
        "indexing": status(),
        "documents": documents,
        "document": current,
        "sections": list(current.sections.all()) if current else [],
        "document_count": len(documents),
        "section_count": total,
        "stale": PlatformKnowledgeSection.objects.filter(embedding__isnull=True).count(),
        "last_embedded": max([doc.embedded_at for doc in documents if doc.embedded_at] or [None]),
        "prompt": system_prompt(),
        "prompt_is_default": system_prompt() == DEFAULT_PROMPT,
        "showing_prompt": selected == "prompt",
    }


def plan_choices():
    """Tier list for the targeting pickers on promos and announcements."""
    from apps.billing.models import Plan

    return list(Plan.objects.filter(is_active=True).order_by("sort_order", "slug"))


def promo_campaign_rows():
    from .public import campaign_rows

    return campaign_rows()


def page(request, **context):
    return render(request, "platform_ops/console.html", context, status=context.pop("status", 200))


def role_for(request):
    if not request.user.is_authenticated or not request.user.is_active or not request.user.is_staff:
        return None
    return PlatformRole.objects.filter(user=request.user, active=True).first()


def valid_uuid_or_none(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def valid_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise Http404 from None


def login_allowed(request, identifier):
    keys = [
        "ops-login:" + hashlib.sha256(value.encode()).hexdigest()
        for value in [
            "account:" + identifier.casefold()[:254],
            "ip:" + client_ip(request),
        ]
    ]
    for key in keys:
        if not cache.add(key, 1, timeout=900):
            try:
                if cache.incr(key) > 10:
                    return False
            except ValueError:
                return False
    return True


def protected(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            role = role_for(request)
            if not role:
                return redirect("/ops/login/")
            proof = request.session.get("platform_mfa", {})
            if (
                not role.otp_confirmed
                or proof.get("version") != role.version
                or proof.get("until", 0) <= time.time()
            ):
                return redirect("/ops/mfa/")
            if roles and role.role not in roles:
                return HttpResponseForbidden("Your platform role cannot perform this action.")
            request.platform_role = role
            return view(request, *args, **kwargs)

        return wrapped

    return decorate


def sign_in(request):
    error = ""
    if request.method == "POST":
        # Count failures by client and account, without persisting raw login names.
        identifier = str(request.POST.get("username", "")).casefold()[:254]
        if not login_allowed(request, identifier):
            return page(
                request,
                screen="login",
                error="Too many attempts. Try again in 15 minutes.",
                status=429,
            )
        user = authenticate(
            request,
            username=request.POST.get("username", ""),
            password=request.POST.get("password", ""),
        )
        role = PlatformRole.objects.filter(user=user, active=True).first() if user else None
        if user and user.is_staff and role:
            login(request, user)
            request.session.pop("platform_mfa", None)
            request.session["platform_password_at"] = time.time()
            record(user, "platform.password_verified")
            return redirect("/ops/mfa/")
        error = "Invalid credentials or platform access unavailable."
    return page(request, screen="login", error=error)


def mfa(request):
    role = role_for(request)
    if not role or request.session.get("platform_password_at", 0) < time.time() - 600:
        return redirect("/ops/login/")
    with transaction.atomic():
        role = PlatformRole.objects.select_for_update().get(pk=role.pk)
        if not role.otp_secret:
            role.otp_secret = new_secret()
            role.save(update_fields=["otp_secret"])
    error = ""
    if request.method == "POST":
        if verify_otp(role.pk, request.POST.get("code", "")):
            request.session.cycle_key()
            request.session["platform_mfa"] = {"version": role.version, "until": time.time() + 1800}
            record(request.user, "platform.mfa_verified")
            return redirect("/ops/")
        error = "Invalid, reused or locked code."
    return page(
        request, screen="mfa", secret=role.otp_secret if not role.otp_confirmed else "", error=error
    )


@require_POST
def sign_out(request):
    if role_for(request):
        record(request.user, "platform.logout")
    logout(request)
    return redirect("/ops/login/")


@protected()
def dashboard(request):
    from django.conf import settings
    from redis import Redis, RedisError

    from apps.agents.models import UsageRecord
    from apps.billing.models import BillingAccount
    from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
    from apps.crm.models import Message

    from .metrics import revenue_metrics
    from .models import DailyMetric

    start = timezone.now() - timedelta(days=30)
    query = request.GET.get("q", "")[:100]
    matches = Q(name__icontains=query)
    try:
        matches |= Q(pk=uuid.UUID(query))
    except ValueError:
        pass
    workspaces = Workspace.objects.filter(matches).annotate(
        total_cost=Sum("usagerecord__cost", filter=Q(usagerecord__created_at__gte=start)),
        total_calls=Count("usagerecord", filter=Q(usagerecord__created_at__gte=start)),
    )
    sort = request.GET.get("sort", "")
    workspaces = workspaces.order_by(
        {"cost": "-total_cost", "calls": "-total_calls"}.get(sort, "name"), "pk"
    )
    workspace_page = Paginator(workspaces, 25).get_page(request.GET.get("page"))
    metric_calls = dict(
        DailyMetric.objects.filter(day__gte=start.date(), name__startswith="meta.calls:")
        .values("name")
        .annotate(total=Sum("value"))
        .values_list("name", "total")
    )
    rows = []
    from .capabilities import CAPABILITIES
    from .models import WorkspaceCapability

    grants = {
        (item.workspace_id, item.key): item
        for item in WorkspaceCapability.objects.filter(workspace_id__in=workspace_page.object_list)
    }
    for workspace in workspace_page:
        account = BillingAccount.objects.for_workspace(workspace).first()
        usage = (
            UsageRecord.objects.for_workspace(workspace)
            .filter(created_at__gte=start)
            .aggregate(tokens=Sum("input_tokens"), cost=Sum("cost"), calls=Count("id"))
        )
        rows.append(
            {
                "workspace": workspace,
                "capabilities": [
                    {
                        "key": key,
                        "label": label,
                        "enabled": bool(
                            grants.get((workspace.pk, key)) and grants[(workspace.pk, key)].enabled
                        ),
                    }
                    for key, label in CAPABILITIES.items()
                ],
                "meta_calls": metric_calls.get("meta.calls:" + str(workspace.pk), 0),
                "account": account,
                "usage": usage,
                "channels": ChannelConnection.objects.for_workspace(workspace).count(),
                "failed": WebhookEvent.objects.for_workspace(workspace)
                .filter(status="failed")
                .count(),
                "suspended": Control.objects.filter(
                    scope=str(workspace.pk), key="workspace", disabled=True
                ).exists(),
            }
        )
    totals = UsageRecord.all_objects.filter(created_at__gte=start).aggregate(
        cost=Sum("cost"), tokens=Sum("input_tokens"), calls=Count("id")
    )
    try:
        redis = Redis.from_url(settings.REDIS_URL, socket_timeout=1, socket_connect_timeout=1)
        bucket = {
            "used": int(redis.get("rate:meta:app") or 0),
            "ttl": max(0, redis.ttl("rate:meta:app")),
            "limit": settings.META_APP_CALLS_PER_HOUR,
        }
    except RedisError:
        bucket = {"unavailable": True}
    tab = request.GET.get("tab", "overview")
    if tab not in TABS:
        tab = "overview"
    interval = request.GET.get("interval", "monthly")
    if interval not in {"monthly", "annual"}:
        interval = "monthly"
    sub = request.GET.get("sub", "")[:64]
    people = None
    if tab == "users":
        from . import accounts

        page_obj, cards = accounts.user_rows(
            query=request.GET.get("q", "")[:100],
            status=request.GET.get("status", ""),
            tier=request.GET.get("tier", "")[:40],
            category=request.GET.get("category", "")[:80],
            joined=request.GET.get("joined", ""),
            page=request.GET.get("page") or 1,
        )
        history_for = None
        if sub.startswith("history-") and sub[8:].isdigit():
            from apps.tenants.models import User

            target = User.objects.filter(pk=int(sub[8:])).first()
            if target:
                history_for = {"user": target, "rows": accounts.history_for(target)}
        from .models import SegmentCategory

        people = {
            "page": page_obj,
            "cards": cards,
            "leaderboard": accounts.leaderboard(),
            "history": history_for,
            "sent": request.GET.get("sent") == "1",
            "categories": list(SegmentCategory.objects.filter(is_active=True)),
            "filters": {
                key: request.GET.get(key, "")
                for key in ["q", "status", "tier", "category", "joined"]
            },
        }
    metrics = None
    if tab == "overview":
        from .metrics import PlatformMetricsService

        try:
            days = int(request.GET.get("days", 30))
        except ValueError:
            days = 30
        metrics = PlatformMetricsService(
            source=request.GET.get("source", "database"), days=days
        ).snapshot()
    return page(
        request,
        screen="dashboard",
        tab=tab,
        interval=interval,
        tiers=tier_rows(),
        workspace_page=workspace_page,
        revenue=revenue_metrics(),
        billing_sync=cache.get("ops:billing_sync", "Not yet synchronized"),
        provider_metrics=DailyMetric.objects.filter(day__gte=start.date())
        .exclude(name__contains=":")
        .values("name")
        .annotate(total=Sum("value")),
        bucket=bucket,
        rows=rows,
        totals=totals,
        messages=Message.all_objects.filter(created_at__gte=start).count(),
        plans=BillingAccount.all_objects.annotate(
            plan=Coalesce(F("plan_price__plan__slug"), Value(settings.DEFAULT_PLAN_SLUG))
        )
        .values("plan", "billing_interval", "status")
        .annotate(total=Count("id"))
        .order_by("plan", "billing_interval", "status"),
        trials=BillingAccount.all_objects.filter(status="trialing", trial_ends_at__isnull=False)
        .select_related("workspace")
        .order_by("trial_ends_at")[:50],
        past_due=BillingAccount.all_objects.filter(status__in=["past_due", "unpaid"])
        .select_related("workspace")
        .order_by("period_end")[:50],
        delivery=Delivery.all_objects.filter(created_at__gte=start)
        .values("status")
        .annotate(total=Count("id")),
        connections=ChannelConnection.all_objects.select_related("workspace").order_by(
            "expires_at"
        )[:100],
        controls=Control.objects.filter(disabled=True),
        statuses=OperationStatus.objects.all(),
        staff=PlatformRole.objects.select_related("user").all(),
        invitations=PlatformInvite.objects.filter(
            used_at__isnull=True, expires_at__gt=timezone.now()
        ).order_by("expires_at")[:100]
        if request.platform_role.role == "owner"
        else [],
        logs=PlatformAudit.objects.all()[:100],
        role=request.platform_role.role,
        backlog=backlog_summary(cache.get("operations:backlogs")),
        credit_revenue_dollars=credit_revenue_dollars(),
        funnel=funnel_dataset(),
        analytics=analytics_dataset(),
        website=website_stats_dataset(first_touch=request.GET.get("touch") == "first"),
        segments=segments_dataset(),
        blog=blog_dataset(
            days=int(request.GET["days"]) if request.GET.get("days", "").isdigit() else 90,
            editing=sub[5:] if sub.startswith("edit-") else "",
        ),
        tickets=support_tickets_dataset(sub if sub in {"billing", "support", "bug"} else "billing"),
        notices=notifications_dataset(
            sub if sub in {"popup", "strip"} else "",
            editing=request.GET.get("edit", ""),
        ),
        templates=email_templates_dataset(),
        credits=ai_credit_context(
            start,
            query=request.GET.get("q", "")[:100] if tab == "ai_credits" else "",
            kind=request.GET.get("type", "") if tab == "ai_credits" else "",
            page=request.GET.get("page") or 1,
            unit=request.GET.get("unit", "m"),
        ),
        rate_unit=request.GET.get("unit", "m") if request.GET.get("unit") in RATE_UNITS else "m",
        rate_units=RATE_UNITS,
        rate_fields=[
            ("Input", "input"),
            ("Output", "output"),
            ("Cache read", "cache_read"),
            ("Cache write", "cache_write"),
        ],
        accounts=automation_accounts(),
        automation_history=(
            automation_runs(request.GET.get("runs", ""))
            if tab == "automations" and valid_uuid_or_none(request.GET.get("runs", ""))
            else None
        ),
        agent=agent_config_context(sub),
        offers=promo_campaign_rows(),
        audit_run=billing_audit_context(),
        all_plans=plan_choices(),
        email_hook=PlatformSetting.get("email_automation_url"),
        saved=request.GET.get("saved") == "1",
        sub=sub,
        metrics=metrics,
        people=people,
    )


@require_POST
@protected("owner")
def settings_save(request):
    """Console-managed platform settings. Only keys listed here can be written, so a
    stray field name can never create a setting the rest of the code does not read."""
    from django.core.exceptions import ValidationError
    from django.core.validators import URLValidator

    url = request.POST.get("email_automation_url", "").strip()[:500]
    if url:
        try:
            URLValidator(schemes=["https"])(url)
        except ValidationError:
            return HttpResponseForbidden("Use an https URL for the email automation endpoint.")
    PlatformSetting.objects.update_or_create(key="email_automation_url", defaults={"value": url})
    record(request.user, "settings.changed", key="email_automation_url")
    return redirect("/ops/?tab=settings&saved=1")


@protected()
def knowledge_indexing_status(request):
    from django.http import JsonResponse

    from .knowledge_indexing import status

    response = JsonResponse(status())
    response["Cache-Control"] = "no-store"
    return response


@require_POST
@protected("owner")
@transaction.atomic
def capability_change(request):
    from .capabilities import CAPABILITIES
    from .models import WorkspaceCapability

    workspace = get_object_or_404(
        Workspace.objects.select_for_update(), pk=valid_uuid(request.POST.get("workspace", ""))
    )
    key = request.POST.get("key", "")
    reason = request.POST.get("reason", "").strip()
    enabled = request.POST.get("enabled")
    if key not in CAPABILITIES or enabled not in {"true", "false"}:
        return HttpResponseForbidden(
            "Choose a known feature and an explicit grant or revoke action."
        )
    if not reason or len(reason) > 300:
        return HttpResponseForbidden("Provide a reason of up to 300 characters.")
    WorkspaceCapability.objects.update_or_create(
        workspace=workspace,
        key=key,
        defaults={"enabled": enabled == "true", "reason": reason},
    )
    record(
        request.user,
        "capability.changed",
        workspace.pk,
        key=key,
        enabled=enabled == "true",
        reason=reason,
    )
    return redirect("/ops/?tab=operations&q=" + str(workspace.pk))


@require_POST
@protected("owner", "support")
@transaction.atomic
def control(request):
    scope = request.POST.get("workspace", "").strip()
    if scope:
        scope = valid_uuid(scope)
        get_object_or_404(Workspace, pk=scope)
    key = request.POST.get("key", "")
    allowed = {
        "workspace",
        "ai",
        "messaging",
        "automations",
        "content",
        "marketplace",
        "integration:google_calendar",
        "integration:calcom",
        "integration:airtable",
        "integration:notion",
        "integration:gohighlevel",
        "integration:slack",
        "integration:attio",
        "integration:elevenlabs",
        "integration:stripe",
        "integration:instagram",
        "integration:whatsapp",
        "integration:telegram",
        "integration:messenger",
    }
    if key.startswith("automation:") and scope:
        from apps.automations.models import Automation

        get_object_or_404(
            Automation.objects.for_workspace(scope), pk=valid_uuid(key.removeprefix("automation:"))
        )
    elif key not in allowed:
        return HttpResponseForbidden("Unknown control.")
    if not scope and request.platform_role.role != "owner":
        return HttpResponseForbidden("Only platform owners can change global controls.")
    reason = request.POST.get("reason", "").strip()[:300]
    if not reason:
        return HttpResponseForbidden("A reason is required.")
    if request.POST.get("disabled") not in {"true", "false"}:
        return HttpResponseForbidden("Choose pause or resume explicitly.")
    disabled = request.POST.get("disabled") == "true"
    item, _ = Control.objects.update_or_create(
        scope=scope, key=key, defaults={"disabled": disabled, "reason": reason}
    )
    record(request.user, "control.changed", scope, key=key, disabled=disabled, reason=reason)
    return redirect("/ops/?tab=controls")


@require_POST
@protected("owner")
@transaction.atomic
def staff_change(request):
    # Lock every role in stable order to protect the last active owner.
    list(PlatformRole.objects.select_for_update().order_by("pk"))
    if not str(request.POST.get("id", "")).isdigit():
        raise Http404
    target = get_object_or_404(PlatformRole, pk=request.POST.get("id"))
    role = request.POST.get("role")
    active = request.POST.get("active") == "true"
    if role not in {"owner", "support", "analyst"}:
        return HttpResponseForbidden("Unknown role.")
    if (
        target.role == "owner"
        and target.active
        and (not active or role != "owner")
        and PlatformRole.objects.filter(role="owner", active=True).count() <= 1
    ):
        return HttpResponseForbidden("The last platform owner cannot be removed.")
    target.role = role
    target.active = active
    target.version += 1
    target.save()
    record(request.user, "staff.changed", target=str(target.user_id), role=role, active=active)
    return redirect("/ops/?tab=team")


@require_POST
@protected("owner")
def invite(request):
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    email = request.POST.get("email", "").strip().lower()
    role = request.POST.get("role", "")
    try:
        validate_email(email)
    except ValidationError:
        return HttpResponseForbidden("Valid email required.")
    if role not in {"owner", "support", "analyst"}:
        return HttpResponseForbidden("Unknown role.")
    token = secrets.token_urlsafe(32)
    with transaction.atomic():
        PlatformInvite.objects.create(
            email=email,
            role=role,
            digest=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(days=1),
        )
        record(request.user, "staff.invited", email=email, role=role)
    return page(request, screen="invite", token=token)


@require_POST
@protected("owner")
@transaction.atomic
def revoke_invite(request):
    if not request.POST.get("id", "").isdigit():
        raise Http404
    item = get_object_or_404(
        PlatformInvite.objects.select_for_update(), pk=request.POST["id"], used_at__isnull=True
    )
    item.expires_at = timezone.now()
    item.save(update_fields=["expires_at"])
    record(request.user, "staff.invite_revoked", target=str(item.pk))
    return redirect("/ops/?tab=team")


def accept_invite(request):
    error = ""
    if request.method == "POST":
        if not login_allowed(request, request.POST.get("username", "")):
            return page(
                request,
                screen="accept",
                error="Too many attempts. Try again in 15 minutes.",
                status=429,
            )
        # Invitees use their existing account password; invitation possession alone is insufficient.
        user = authenticate(
            request,
            username=request.POST.get("username", ""),
            password=request.POST.get("password", ""),
        )
        if user:
            with transaction.atomic():
                invitation = (
                    PlatformInvite.objects.select_for_update()
                    .filter(
                        digest=hashlib.sha256(request.POST.get("token", "").encode()).hexdigest(),
                        email__iexact=user.email,
                        used_at__isnull=True,
                        expires_at__gt=timezone.now(),
                    )
                    .first()
                )
                if invitation and not PlatformRole.objects.filter(user=user).exists():
                    user.is_staff = True
                    user.save(update_fields=["is_staff"])
                    PlatformRole.objects.create(user=user, role=invitation.role)
                    invitation.used_at = timezone.now()
                    invitation.save()
                    record(user, "staff.invite_accepted")
                    return redirect("/ops/login/")
        error = "Invitation or credentials invalid."
    return page(request, screen="accept", error=error)


@require_POST
@protected("owner", "support")
def start_support(request):
    workspace = get_object_or_404(Workspace, pk=valid_uuid(request.POST.get("workspace")))
    reason = request.POST.get("reason", "").strip()[:300]
    if not reason:
        return HttpResponseForbidden("A support reason is required.")
    with transaction.atomic():
        session = SupportSession.objects.create(
            operator=request.platform_role,
            workspace=workspace,
            reason=reason,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        record(
            request.user, "support.started", workspace.pk, session=str(session.pk), reason=reason
        )
    return redirect(f"/ops/support/{session.pk}/")


@protected("owner", "support")
def support(request, pk):
    from apps.crm.models import Conversation, Message

    session = get_object_or_404(
        SupportSession.objects.select_related("workspace"),
        pk=pk,
        operator=request.platform_role,
        ended_at__isnull=True,
        expires_at__gt=timezone.now(),
    )
    if request.method == "POST":
        with transaction.atomic():
            session.ended_at = timezone.now()
            session.save()
            record(request.user, "support.ended", session.workspace_id, session=str(session.pk))
        return redirect("/ops/?tab=workspaces")
    record(request.user, "support.viewed", session.workspace_id, session=str(session.pk))
    return page(
        request,
        screen="support",
        support=session,
        conversations=Conversation.objects.for_workspace(session.workspace_id).select_related(
            "identity__lead"
        )[:50],
        messages=Message.objects.for_workspace(session.workspace_id).order_by("-created_at")[:50],
    )


@require_POST
@protected("owner")
def operation_status(request):
    from django.utils.dateparse import parse_datetime

    provider = request.POST.get("provider", "")
    if provider not in {"instagram", "whatsapp", "messenger", "telegram"}:
        return HttpResponseForbidden("Unknown provider.")
    raw_expiry = request.POST.get("certificate_expires_at", "").strip()
    try:
        expiry = parse_datetime(raw_expiry) if raw_expiry else None
    except ValueError:
        expiry = None
    if raw_expiry and (not expiry or timezone.is_naive(expiry)):
        return page(
            request,
            error="Use an ISO date and time with timezone for certificate expiry.",
            status=400,
        )
    with transaction.atomic():
        OperationStatus.objects.update_or_create(
            provider=provider,
            defaults={
                "review_status": request.POST.get("review_status", "")[:100],
                "permissions": request.POST.get("permissions", "")[:1000],
                "certificate_expires_at": expiry,
            },
        )
        record(
            request.user,
            "operations.updated",
            provider=provider,
            review_status=request.POST.get("review_status", "")[:100],
            permissions=request.POST.get("permissions", "")[:1000],
            certificate_expiry=raw_expiry,
        )
    return redirect("/ops/?tab=operations")


def credit_revenue_dollars():
    """AI credit purchases across all tenants: separate from subscription MRR."""
    from decimal import Decimal

    from apps.billing.models import AICreditTransaction

    cents = AICreditTransaction.all_objects.filter(
        type__in=["topup", "auto_topup"], status="complete"
    ).aggregate(total=Sum("amount_cents"))["total"] or Decimal(0)
    return f"{cents / 100:,.2f}"


def tier_rows():
    from apps.billing.models import BillingAccount, Plan

    rows = []
    for plan in Plan.objects.prefetch_related("prices").order_by("is_custom", "sort_order", "slug"):
        rows.append(
            {
                "plan": plan,
                "limits": plan.limits,
                "prices": {price.billing_interval: price for price in plan.prices.all()},
                "subscribers": BillingAccount.all_objects.filter(plan_price__plan=plan).count(),
            }
        )
    return rows


def number_or_none(value):
    value = (value or "").strip()
    return int(value) if value else None


@require_POST
@protected("owner")
@transaction.atomic
def tier_save(request, pk=None):
    """Create or edit a tier. Default (public) tiers only accept Stripe wiring and their
    active flag here: their prices and limits change through a migration and a customer
    notice, never a click. Custom tiers are fully editable and deletable."""
    from django.db.models import ProtectedError
    from django.utils.text import slugify

    from apps.billing.models import Plan, PlanLimits, PlanPrice

    data = request.POST
    if pk is None:
        slug = slugify(data.get("slug") or data.get("name", ""))[:40]
        if not slug or Plan.objects.filter(slug=slug).exists():
            return HttpResponseForbidden("Choose a unique tier slug.")
        plan = Plan.objects.create(slug=slug, name=slug, is_custom=True)
        PlanLimits.objects.create(plan=plan)
    else:
        plan = get_object_or_404(Plan.objects.select_for_update(), pk=pk)
    if data.get("action") == "delete":
        if not plan.is_custom:
            return HttpResponseForbidden("Default tiers cannot be deleted; retire them instead.")
        try:
            plan.delete()
        except ProtectedError:
            return HttpResponseForbidden("This tier still has subscribers. Move them first.")
        record(request.user, "tier.deleted", slug=plan.slug)
        return redirect("/ops/?tab=tiers")
    try:
        if plan.is_custom:
            plan.name = data.get("name", "").strip()[:60] or plan.slug
            plan.partner_label = data.get("partner_label", "").strip()[:60]
            plan.sort_order = number_or_none(data.get("sort_order")) or 50
            plan.is_featured = data.get("is_featured") == "on"
            limits = plan.limits
            for name in PlanLimits.NUMERIC:
                setattr(limits, name, number_or_none(data.get(name)))
            for name in PlanLimits.FLAGS:
                setattr(limits, name, data.get(name) == "on")
            limits.save()
        for interval in ["monthly", "annual"]:
            defaults = {
                "stripe_price_id": data.get(f"{interval}_stripe_price_id", "").strip()[:100],
                "stripe_meter_price_id": data.get(f"{interval}_stripe_meter_price_id", "").strip()[
                    :100
                ],
            }
            if plan.is_custom:
                defaults["price_cents"] = number_or_none(data.get(f"{interval}_price_cents")) or 0
            PlanPrice.objects.update_or_create(
                plan=plan, billing_interval=interval, defaults=defaults
            )
    except ValueError:
        return HttpResponseForbidden("Limits and prices must be whole numbers.")
    plan.is_active = data.get("is_active") == "on"
    plan.save()
    record(request.user, "tier.saved", slug=plan.slug, custom=plan.is_custom)
    return redirect("/ops/?tab=tiers")


BACKLOG_LABELS = {
    "webhookevent": "Inbound events waiting over 5 minutes",
    "delivery": "Deliveries waiting over 5 minutes",
    "agentrun": "Agent runs waiting over 5 minutes",
    "webhookevent_failed": "Inbound events failed in the last hour",
}


def backlog_summary(counts):
    """Shape the worker-computed backlog counts for display: a total for the tile and
    labelled rows for the breakdown. None means the check has not run recently."""
    if not counts:
        return {"known": False, "total": 0, "items": []}
    items = [(BACKLOG_LABELS.get(key, key), value) for key, value in counts.items()]
    return {"known": True, "total": sum(counts.values()), "items": items}
