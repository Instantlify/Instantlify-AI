"""Services behind the growth-side console sections.

Everything here operates on platform-owned tables (signup funnel, marketing-site
visits, segments, tickets, promos, announcements, transactional email). None of it
is tenant-scoped, and no tenant API may read another tenant's rows through it.
"""

import hashlib
import re
import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    Announcement,
    AnnouncementView,
    BlogPost,
    BlogPostView,
    EmailTemplate,
    PageSignup,
    PageVisit,
    PlatformSetting,
    PromoCampaign,
    PromoCampaignEvent,
    SignupFunnelEvent,
    SupportTicket,
)

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


# ------------------------------------------------------------------ signup funnel


def record_funnel_event(*, flow, step, status, user=None, workspace=None, is_owner=True):
    """Write one wizard/tour transition. Unknown steps are rejected rather than
    silently recorded, so a renamed step in the frontend shows up as a failure here
    instead of as a funnel that quietly stops counting."""
    steps = SignupFunnelEvent.WIZARD_STEPS if flow == "wizard" else SignupFunnelEvent.TOUR_STEPS
    if flow not in {"wizard", "tour"} or step not in steps:
        raise ValueError(f"Unknown {flow} step: {step}")
    if status not in SignupFunnelEvent.STATUSES:
        raise ValueError(f"Unknown funnel status: {status}")
    return SignupFunnelEvent.objects.create(
        flow=flow,
        step=step,
        status=status,
        user=user,
        workspace=workspace,
        is_owner=is_owner,
    )


def wizard_progress(user):
    """Where to resume someone who closed the tab mid-wizard. Returns the first step
    they have neither completed nor skipped — a wizard that restarts at step one on
    every return visit reports worse funnel numbers than the product deserves."""
    done = set(
        SignupFunnelEvent.objects.filter(
            user=user, flow="wizard", status__in=["completed", "skipped"]
        ).values_list("step", flat=True)
    )
    for step in SignupFunnelEvent.WIZARD_STEPS:
        if step not in done:
            return {"step": step, "completed": sorted(done), "finished": False}
    return {"step": None, "completed": sorted(done), "finished": True}


def funnel_report(flow="wizard"):
    """Per-step reached/completed/skipped counted by DISTINCT user, plus drop-off
    from the previous step. Counting rows instead of users would let one person
    refreshing a page look like traffic."""
    steps = SignupFunnelEvent.WIZARD_STEPS if flow == "wizard" else SignupFunnelEvent.TOUR_STEPS
    events = SignupFunnelEvent.objects.filter(flow=flow)
    rows, previous_reached, worst = [], None, None
    for step in steps:
        scoped = events.filter(step=step)
        counts = {
            status: scoped.filter(status=status).values("user_id").distinct().count()
            for status in SignupFunnelEvent.STATUSES
        }
        drop = None
        if previous_reached:
            drop = round((previous_reached - counts["reached"]) * 100 / previous_reached)
        rows.append(
            {
                "name": step,
                "reached": counts["reached"],
                "completed": counts["completed"],
                "skipped": counts["skipped"],
                "drop_off": f"{drop}%" if drop is not None else "—",
                "drop_value": drop or 0,
            }
        )
        previous_reached = counts["reached"] or previous_reached
    widest = max([row["reached"] for row in rows] or [0]) or 1
    for row in rows:
        row["width_pct"] = max(18, round(row["reached"] * 100 / widest))
    ranked = [row for row in rows if row["drop_value"]]
    if ranked:
        worst = max(ranked, key=lambda row: row["drop_value"])
        worst["alert"] = True
    return {"steps": rows, "worst": worst}


# --------------------------------------------------------------- marketing site


def record_page_visit(*, page, session_id, source="", referrer=""):
    """A visit from the public marketing site. The first session a visitor is seen
    in carries first-touch credit; later visits from another source do not steal it."""
    first = not PageVisit.objects.filter(session_id=session_id).exists()
    return PageVisit.objects.create(
        page=page[:200],
        session_id=session_id[:64],
        source=(source or source_from_referrer(referrer))[:120],
        referrer=referrer[:500],
        is_first_touch=first,
    )


def source_from_referrer(referrer):
    if not referrer:
        return "Direct / Unknown"
    host = re.sub(r"^https?://", "", referrer).split("/")[0].lower()
    return host.removeprefix("www.")[:120] or "Direct / Unknown"


def record_page_signup(*, session_id, page, user=None):
    """Attributes a completed signup to its visit session. Idempotent: a retried
    signup call must not double-count a conversion."""
    first_touch = (
        PageVisit.objects.filter(session_id=session_id, is_first_touch=True)
        .values_list("source", flat=True)
        .first()
    )
    latest = (
        PageVisit.objects.filter(session_id=session_id).values_list("source", flat=True).first()
    )
    try:
        with transaction.atomic():
            return PageSignup.objects.create(
                session_id=session_id[:64],
                page=page[:200],
                source=(latest or "Direct / Unknown")[:120],
                first_touch_source=(first_touch or latest or "Direct / Unknown")[:120],
                user=user,
            )
    except IntegrityError:
        return PageSignup.objects.filter(session_id=session_id).first()


def page_stats(page, *, now=None, first_touch=False):
    now = now or timezone.now()
    visits = PageVisit.objects.filter(page=page)
    signups = PageSignup.objects.filter(page=page)

    def window(days):
        since = now - timedelta(days=days)
        return {
            "visitors": visits.filter(created_at__gte=since)
            .values("session_id")
            .distinct()
            .count(),
            "signups": signups.filter(created_at__gte=since).count(),
        }

    all_time_visitors = visits.values("session_id").distinct().count()
    all_time_signups = signups.count()
    return {
        "name": page,
        "path": page,
        "all_time": {"visitors": all_time_visitors, "signups": all_time_signups},
        "last_30": window(30),
        "last_7": window(7),
        "conversion": (
            f"{all_time_signups * 100 / all_time_visitors:.1f}%" if all_time_visitors else "0.0%"
        ),
        "sources": source_breakdown(visits, first_touch=first_touch),
    }


def source_breakdown(visits, *, first_touch=False):
    scoped = visits.filter(is_first_touch=True) if first_touch else visits
    counts = {}
    for source in scoped.values_list("source", flat=True):
        counts[source or "Direct / Unknown"] = counts.get(source or "Direct / Unknown", 0) + 1
    total = sum(counts.values()) or 1
    return [
        {"name": name, "count": count, "pct": round(count * 100 / total)}
        for name, count in sorted(counts.items(), key=lambda item: -item[1])[:10]
    ]


# ----------------------------------------------------------------------- blog


def record_blog_view(*, post, session_id, scroll_depth_pct=0, time_spent_seconds=0):
    """One row per (post, session), updated in place as the reader scrolls — the
    deepest scroll and longest dwell win, so a beacon that fires repeatedly during
    one read does not inflate the view count."""
    view, created = BlogPostView.objects.get_or_create(
        post=post,
        session_id=session_id[:64],
        defaults={
            "scroll_depth_pct": min(100, scroll_depth_pct),
            "time_spent_seconds": time_spent_seconds,
        },
    )
    if not created:
        view.scroll_depth_pct = max(view.scroll_depth_pct, min(100, scroll_depth_pct))
        view.time_spent_seconds = max(view.time_spent_seconds, time_spent_seconds)
        view.save(update_fields=["scroll_depth_pct", "time_spent_seconds"])
    return view


def blog_analytics(days=90):
    from django.db.models import Avg, Count
    from django.db.models.functions import TruncDate

    since = timezone.now() - timedelta(days=days)
    views = BlogPostView.objects.filter(created_at__gte=since)
    total = views.count()
    aggregate = views.aggregate(scroll=Avg("scroll_depth_pct"), spent=Avg("time_spent_seconds"))
    completed = views.filter(scroll_depth_pct__gte=90).count()
    top = (
        views.values("post__title", "post__slug")
        .annotate(total=Count("id"), scroll=Avg("scroll_depth_pct"))
        .order_by("-total")[:8]
    )
    per_day = dict(
        views.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .values_list("day", "total")
    )
    today = timezone.now().date()
    daily = [
        {
            "day": today - timedelta(days=offset),
            "total": per_day.get(today - timedelta(days=offset), 0),
        }
        for offset in range(days - 1, -1, -1)
    ]
    peak = max([row["total"] for row in daily] or [0]) or 1
    for row in daily:
        row["height"] = round(row["total"] * 100 / peak)
    return {
        "days": days,
        "daily": daily,
        "views": total,
        "scroll_depth": f"{aggregate['scroll'] or 0:.0f}%",
        "completion": f"{completed * 100 / total:.0f}%" if total else "0%",
        "time_spent": f"{aggregate['spent'] or 0:.0f}s",
        "range_start": f"{since.strftime('%b')} {since.day}",
        "top": [
            {
                "title": row["post__title"],
                "slug": row["post__slug"],
                "views": row["total"],
                "scroll": f"{row['scroll'] or 0:.0f}%",
            }
            for row in top
        ],
    }


def published_posts():
    return BlogPost.objects.filter(status="published").select_related("category")


# -------------------------------------------------------------------- tickets


def new_ticket_number():
    return "#" + str(secrets.randbelow(9_000_000_000) + 1_000_000_000)


def open_ticket(
    *,
    subject,
    reporter_email,
    category="support",
    body="",
    reporter_name="",
    reporter_channel="",
    workspace=None,
    by_agent=False,
):
    """The one way a ticket is created. The support form and the platform agent's
    `create_ticket` tool both come through here, so neither can skip validation."""
    subject = (subject or "").strip()
    reporter_email = (reporter_email or "").strip()
    if not subject:
        raise ValueError("A ticket needs a subject.")
    if not reporter_email:
        raise ValueError("A ticket needs a reporter email.")
    if category not in SupportTicket.CATEGORIES:
        raise ValueError(f"Unknown ticket category: {category}")
    for _ in range(5):
        try:
            with transaction.atomic():
                return SupportTicket.objects.create(
                    ticket_number=new_ticket_number(),
                    category=category,
                    subject=subject[:200],
                    body=body or "",
                    reporter_name=reporter_name[:120],
                    reporter_email=reporter_email[:254],
                    reporter_channel=reporter_channel[:30],
                    workspace=workspace,
                    opened_by_agent=by_agent,
                )
        except IntegrityError:
            continue
    raise RuntimeError("Could not allocate a ticket number.")


def ticket_counts():
    return {
        category: SupportTicket.objects.filter(category=category).count()
        for category in SupportTicket.CATEGORIES
    }


# ------------------------------------------------------------ promos + notices


def live_campaign_for(workspace, *, interval=None, plan=None):
    """The campaign to show this workspace, if any. A campaign with no target plans
    means every paid plan."""
    campaigns = PromoCampaign.objects.filter(is_live=True).prefetch_related("target_plans")
    for campaign in campaigns:
        if interval and campaign.target_interval not in {"both", interval}:
            continue
        targets = list(campaign.target_plans.all())
        if targets and plan and plan not in targets:
            continue
        return campaign
    return None


def record_campaign_event(campaign, event_type, *, workspace=None, user=None):
    if event_type not in PromoCampaignEvent.EVENTS:
        raise ValueError(f"Unknown campaign event: {event_type}")
    return PromoCampaignEvent.objects.create(
        campaign=campaign, event_type=event_type, workspace=workspace, user=user
    )


def campaign_totals(campaign):
    counts = {event: 0 for event in PromoCampaignEvent.EVENTS}
    for row in campaign.events.values("event_type"):
        counts[row["event_type"]] = counts.get(row["event_type"], 0) + 1
    return counts


def coupon_for_checkout(workspace_id, price):
    """The Stripe coupon to attach when this workspace checks out, if it claimed a
    still-live campaign that matches the plan and interval and has not redeemed it.

    Returns {"slug", "coupon"} or None. A promo problem never blocks a checkout: any
    Stripe error here means the customer simply pays full price.
    """
    import stripe
    from django.conf import settings

    claimed = (
        PromoCampaignEvent.objects.filter(
            workspace_id=workspace_id, event_type="claimed", campaign__is_live=True
        )
        .select_related("campaign")
        .order_by("-created_at")
    )
    for event in claimed:
        campaign = event.campaign
        if campaign.events.filter(workspace_id=workspace_id, event_type="redeemed").exists():
            continue
        if campaign.target_interval not in {"both", price.billing_interval}:
            continue
        targets = list(campaign.target_plans.all())
        if targets and price.plan not in targets:
            continue
        # Percent in the id: editing the discount mints a new coupon instead of
        # silently changing one already attached to live subscriptions.
        coupon = f"nemio-promo-{campaign.slug}-{campaign.discount_percent}"
        try:
            try:
                stripe.Coupon.retrieve(coupon, api_key=settings.STRIPE_SECRET_KEY)
            except stripe.InvalidRequestError:
                stripe.Coupon.create(
                    id=coupon,
                    percent_off=campaign.discount_percent,
                    duration="once",
                    name=(campaign.name or campaign.slug)[:40],
                    api_key=settings.STRIPE_SECRET_KEY,
                )
        except stripe.StripeError:
            return None
        return {"slug": campaign.slug, "coupon": coupon}
    return None


def record_redemption(slug, workspace_id, subscription_id):
    """The discount actually landed on a Stripe subscription. Keyed on the subscription
    so a replayed webhook records it once."""
    campaign = PromoCampaign.objects.filter(slug=slug).first()
    if not campaign:
        return None
    try:
        with transaction.atomic():
            return PromoCampaignEvent.objects.create(
                campaign=campaign,
                workspace_id=workspace_id,
                event_type="redeemed",
                reference=str(subscription_id)[:120],
            )
    except IntegrityError:
        return None


def announcements_for(*, page="", plan=None, user=None):
    """Active announcements matching this page and tier, minus any popup this user
    has already seen. Strips repeat; popups are once per viewer."""
    rows = []
    for item in Announcement.objects.filter(is_active=True).prefetch_related("target_plans"):
        pages = item.pages()
        if pages and page not in pages:
            continue
        plans = list(item.target_plans.all())
        if plans and plan not in plans:
            continue
        if item.type == "popup" and user and item.views.filter(user=user).exists():
            continue
        rows.append(item)
    return rows


def record_announcement_view(announcement, *, user=None, session_id=""):
    try:
        with transaction.atomic():
            return AnnouncementView.objects.create(
                announcement=announcement, user=user, session_id=session_id[:64]
            )
    except IntegrityError:
        return announcement.views.filter(user=user).first()


# --------------------------------------------------------- transactional email


class TemplateMissing(Exception):
    """Raised when a caller names a template that does not exist, or is a draft."""


def render_template(template, context):
    def swap(match):
        return str(context.get(match.group(1), match.group(0)))

    return PLACEHOLDER.sub(swap, template)


def send_transactional_email(template_name, to, context=None):
    """The single send path for transactional email. Copy lives in `EmailTemplate`
    keyed by name, so changing an email's wording is a content edit and never a
    deploy. A `draft` row is editable but must never reach a customer."""
    from django.core.mail import EmailMessage

    context = context or {}
    template = EmailTemplate.objects.filter(name=template_name).first()
    if not template:
        raise TemplateMissing(f"No email template named {template_name!r}.")
    if template.status != "active":
        raise TemplateMissing(f"Email template {template_name!r} is a draft and was not sent.")
    message = EmailMessage(
        subject=render_template(template.subject, context),
        body=render_template(template.body, context),
        to=[to],
    )
    message.send(fail_silently=False)
    return {"template": template_name, "to": to, "subject": message.subject}


def email_hook_payload(*, operator, target_user, subject, message):
    """Payload posted to the configured outbound email webhook when an operator
    sends a message from the console. Shape is documented in the Settings page."""
    return {
        "operator_id": str(getattr(operator, "pk", "")),
        "target_user_id": str(getattr(target_user, "pk", "")),
        "target_email": getattr(target_user, "email", ""),
        "subject": subject,
        "message": message,
    }


def outbound_email_hook():
    return PlatformSetting.get("email_automation_url")


def session_key(request):
    """A stable, non-identifying session id for first-party tracking: derived from
    the client's own cookie when present, otherwise from coarse request features.
    Never an email, never a user id."""
    existing = request.COOKIES.get("nm_sid")
    if existing and re.fullmatch(r"[A-Za-z0-9_-]{8,64}", existing):
        return existing
    seed = (
        request.META.get("REMOTE_ADDR", "")
        + request.META.get("HTTP_USER_AGENT", "")[:120]
        + timezone.now().strftime("%Y-%m-%d")
    )
    return hashlib.sha256(seed.encode()).hexdigest()[:32]
