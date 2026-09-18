"""Billing lifecycle emails, sent through the transactional registry.

Two of these deliberately read Stripe at send time rather than local state:

- `plan-changed-v2` composes its billing line from Stripe's live upcoming-invoice
  preview, because Stripe's proration and billing-date logic is the source of truth
  and the local account can drift;
- `manage-subscription-link` creates its billing-portal session immediately before
  sending, because the URL is single-use and expires within minutes. It is never
  generated ahead of time or stored.

Every sender swallows delivery failures after logging them: an email that cannot go
out must never fail the billing event or job that triggered it.
"""

import logging
from datetime import UTC, datetime, timedelta

import stripe
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

log = logging.getLogger(__name__)


def owners(workspace_id):
    from apps.tenants.models import Membership

    return list(
        Membership.all_objects.filter(workspace_id=workspace_id, role="owner").select_related(
            "user", "workspace"
        )
    )


def _send(template, membership, context):
    from apps.platform_ops.growth import TemplateMissing, send_transactional_email

    try:
        send_transactional_email(
            template,
            membership.user.email,
            {
                "name": membership.user.first_name or "there",
                "workspace": membership.workspace.name,
                "billing_url": f"{settings.PUBLIC_APP_URL}/w/{membership.workspace_id}/payments",
                **context,
            },
        )
        return True
    except (TemplateMissing, OSError) as exc:
        log.warning("Billing email not sent", extra={"event_code": template, "detail": str(exc)})
        return False


def _money(cents, currency="usd"):
    return f"{(cents or 0) / 100:,.2f} {str(currency).upper()}"


def billing_line(account):
    """What the customer will be charged next and when, straight from Stripe."""
    if account.status == "trialing" and account.trial_ends_at:
        return f"Your trial ends on {account.trial_ends_at:%B} {account.trial_ends_at.day}."
    if not (settings.STRIPE_SECRET_KEY and account.customer_id and account.subscription_id):
        return "Your new plan is active."
    try:
        preview = stripe.Invoice.create_preview(
            customer=account.customer_id,
            subscription=account.subscription_id,
            api_key=settings.STRIPE_SECRET_KEY,
        )
    except (stripe.StripeError, AttributeError):
        return "Your new plan is active."
    when = preview.get("next_payment_attempt") or preview.get("period_end")
    amount = _money(preview.get("amount_due"), preview.get("currency", "usd"))
    if when:
        date = datetime.fromtimestamp(when, tz=UTC)
        return f"Your next invoice is {amount} on {date:%B} {date.day}."
    return f"Your next invoice is {amount}."


@shared_task(ignore_result=True, soft_time_limit=60, time_limit=90)
def send_plan_changed(workspace_id):
    from .models import BillingAccount

    account = (
        BillingAccount.all_objects.filter(workspace_id=workspace_id)
        .select_related("plan_price__plan")
        .first()
    )
    if not account:
        return 0
    context = {"plan": account.plan_obj.name, "billing_line": billing_line(account)}
    return sum(_send("plan-changed-v2", member, context) for member in owners(workspace_id))


def send_manage_link(account, membership):
    """Creates the portal session at send time; the URL is single-use and short-lived."""
    if not (settings.STRIPE_SECRET_KEY and account.customer_id):
        raise ValueError("This workspace has no Stripe customer yet.")
    session = stripe.billing_portal.Session.create(
        customer=account.customer_id,
        return_url=f"{settings.PUBLIC_APP_URL}/w/{account.workspace_id}/payments",
        api_key=settings.STRIPE_SECRET_KEY,
    )
    return _send("manage-subscription-link", membership, {"portal_url": session.url})


@shared_task(ignore_result=True, soft_time_limit=120, time_limit=150)
def send_trial_reminders():
    """Daily. Each trial ending two to three days from now gets one reminder: the
    window is one day wide and the task runs once a day, and a cache marker guards
    against a double run."""
    from .models import BillingAccount

    now = timezone.now()
    sent = 0
    for account in BillingAccount.all_objects.filter(
        status="trialing",
        trial_ends_at__gte=now + timedelta(days=2),
        trial_ends_at__lt=now + timedelta(days=3),
    ).select_related("plan_price__plan"):
        if not cache.add(f"billing:trial-reminder:{account.pk}", 1, 60 * 60 * 24 * 7):
            continue
        context = {
            "days": 3,
            "plan": account.plan_obj.name,
            "trial_ends": f"{account.trial_ends_at:%B} {account.trial_ends_at.day}",
        }
        sent += sum(_send("trial-ending-soon", m, context) for m in owners(account.workspace_id))
    return sent


def credits_low(workspace_id, balance_cents):
    """Once per day per workspace, so a run of parked turns is one email, not fifty."""
    if not cache.add(f"billing:credits-low:{workspace_id}", 1, 60 * 60 * 24):
        return 0
    return sum(
        _send("credits-low", member, {"balance": _money(balance_cents)})
        for member in owners(workspace_id)
    )


def auto_topup_failed(workspace_id):
    return sum(_send("auto-topup-failed", member, {}) for member in owners(workspace_id))
