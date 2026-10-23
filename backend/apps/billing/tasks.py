import json
import logging
from datetime import UTC, datetime, timedelta

import stripe
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.agents.models import UsageRecord
from apps.tenants.dispatch import enqueue_once
from apps.tenants.services import audit

from .models import BillingAccount, BillingEvent, BillingJob, PlanPrice
from .services import account_for, payments_url, return_url

MAX_REPORT_ATTEMPTS = 10
# Subscription states in which metered usage is billable. Canceled, unpaid or
# incomplete subscriptions must not receive meter events they can never invoice.
METERED_STATUSES = ["active", "past_due"]
CLOSED_STATUSES = {"canceled", "incomplete_expired", "unpaid"}


def reportable_usage():
    # Only usage inside a paid subscription period is metered; trial usage never is.
    # Prepaid-credit workspaces are debited per call; metering them too would double bill.
    return (
        UsageRecord.all_objects.exclude(billing_mode="platform_credits")
        .filter(
            status="complete",
            kind="generation",
            reported_at__isnull=True,
            report_attempts__lt=MAX_REPORT_ATTEMPTS,
            workspace__billingaccount__customer_id__isnull=False,
            workspace__billingaccount__subscription_id__gt="",
            workspace__billingaccount__status__in=METERED_STATUSES,
            created_at__gte=F("workspace__billingaccount__period_start"),
        )
        .filter(Q(report_after__isnull=True) | Q(report_after__lte=timezone.now()))
    )


@shared_task(ignore_result=True)
def dispatch_billing():
    for model, task in [(BillingJob, process_job), (BillingEvent, process_event)]:
        for wid, pk in model.all_objects.filter(status="pending").values_list("workspace_id", "pk")[
            :100
        ]:
            enqueue_once(task, wid, pk)
    if settings.STRIPE_SECRET_KEY:
        for wid, pk in reportable_usage().values_list("workspace_id", "pk")[:100]:
            enqueue_once(report_usage, wid, pk)


@shared_task(ignore_result=True)
def process_job(workspace_id, job_id):
    with transaction.atomic():
        job = BillingJob.objects.for_workspace(workspace_id).select_for_update().get(pk=job_id)
        if job.status != "pending":
            return
        if not settings.STRIPE_SECRET_KEY:
            job.status = "failed"
            job.result = json.dumps({"error": "stripe_not_configured"})
            job.save()
            return
        account = account_for(workspace_id)
        try:
            if not account.customer_id:
                customer = stripe.Customer.create(
                    api_key=settings.STRIPE_SECRET_KEY,
                    metadata={"workspace_id": workspace_id},
                    idempotency_key=f"workspace:{workspace_id}",
                )
                account.customer_id = customer.id
                account.save()
            if job.kind == "credits":
                from .credits import create_topup_session

                session = create_topup_session(job, account)
            elif job.kind == "portal":
                session = stripe.billing_portal.Session.create(
                    api_key=settings.STRIPE_SECRET_KEY,
                    customer=account.customer_id,
                    return_url=payments_url(workspace_id),
                    idempotency_key=str(job.id),
                )
            else:
                price = (
                    PlanPrice.objects.select_related("plan")
                    .filter(
                        plan__slug=job.plan,
                        plan__is_active=True,
                        billing_interval=job.interval or "monthly",
                    )
                    .first()
                )
                if not price or not price.stripe_price_id:
                    raise ValueError("price_not_configured")
                if account.subscription_id and account.status in LIVE_STATUSES:
                    # Already subscribed: a second Checkout would bill twice. Stripe's
                    # portal shows the switch to the chosen plan and prorates it.
                    session = plan_change_session(workspace_id, account, price, job)
                    job.result = json.dumps({"url": session.url})
                    job.status = "complete"
                    job.save()
                    return
                line_items = [{"price": price.stripe_price_id, "quantity": 1}]
                if price.stripe_meter_price_id:
                    line_items.append({"price": price.stripe_meter_price_id})
                subscription_data = {
                    "metadata": {
                        "workspace_id": workspace_id,
                        "plan": job.plan,
                        "interval": price.billing_interval,
                    }
                }
                # One trial per workspace: never on a re-subscribe or an upgrade.
                from apps.platform_ops.growth import coupon_for_checkout

                promotion = coupon_for_checkout(workspace_id, price)
                if promotion:
                    subscription_data["metadata"]["promo_campaign"] = promotion["slug"]
                first_subscription = not account.subscription_id and not account.trial_ends_at
                if settings.STRIPE_TRIAL_DAYS and first_subscription:
                    subscription_data["trial_period_days"] = settings.STRIPE_TRIAL_DAYS
                session = stripe.checkout.Session.create(
                    api_key=settings.STRIPE_SECRET_KEY,
                    customer=account.customer_id,
                    mode="subscription",
                    line_items=line_items,
                    success_url=return_url(job, "?billing=success"),
                    cancel_url=return_url(job, "?billing=cancelled"),
                    subscription_data=subscription_data,
                    idempotency_key=str(job.id),
                    **({"discounts": [{"coupon": promotion["coupon"]}]} if promotion else {}),
                )
            job.result = json.dumps({"url": session.url})
            job.status = "complete"
        except (stripe.StripeError, ValueError) as exc:
            job.status = "failed"
            code = "already_on_plan" if str(exc) == "already_on_plan" else "billing_provider_error"
            job.result = json.dumps({"error": code})
        job.save()


LIVE_STATUSES = {"active", "trialing", "past_due"}


def plan_change_session(workspace_id, account, price, job):
    """A portal session opened on the confirm step for switching to ``price``."""
    subscription = stripe.Subscription.retrieve(
        account.subscription_id, api_key=settings.STRIPE_SECRET_KEY
    )
    items = []
    for item in subscription["items"]["data"]:
        metered = (item["price"].get("recurring") or {}).get("usage_type") == "metered"
        target = price.stripe_meter_price_id if metered else price.stripe_price_id
        if target and target != item["price"]["id"]:
            items.append(
                {"id": item["id"], "price": target, **({} if metered else {"quantity": 1})}
            )
    if not items:
        raise ValueError("already_on_plan")
    return stripe.billing_portal.Session.create(
        api_key=settings.STRIPE_SECRET_KEY,
        customer=account.customer_id,
        return_url=return_url(job, "?billing=success"),
        flow_data={
            "type": "subscription_update_confirm",
            "subscription_update_confirm": {
                "subscription": account.subscription_id,
                "items": items,
            },
            "after_completion": {
                "type": "redirect",
                "redirect": {"return_url": return_url(job, "?billing=success")},
            },
        },
        idempotency_key=str(job.id),
    )


@shared_task(ignore_result=True)
def process_event(workspace_id, event_id):
    with transaction.atomic():
        event = (
            BillingEvent.objects.for_workspace(workspace_id).select_for_update().get(pk=event_id)
        )
        if event.status != "pending":
            return
        try:
            with transaction.atomic():
                event.status = apply_event(workspace_id, json.loads(event.payload), event.id)
        except (KeyError, TypeError, ValueError, BillingAccount.DoesNotExist):
            # Malformed or unexpected events are kept for review, not retried forever.
            event.status = "failed"
        event.save()


def invoice_subscription(invoice):
    """Subscription an invoice bills, across the pre- and post-2025 invoice shapes."""
    details = (invoice.get("parent") or {}).get("subscription_details") or {}
    value = invoice.get("subscription") or details.get("subscription")
    return value.get("id") if isinstance(value, dict) else value


def apply_subscription(account, obj):
    """Map a Stripe subscription object onto the account. Returns audit codes for
    anything an operator should look at."""
    notes = []
    account.subscription_id = obj["id"]
    account.status = obj["status"]
    items = obj.get("items", {}).get("data", [])
    prices = {item["price"]["id"] for item in items}
    matched = (
        PlanPrice.objects.select_related("plan").filter(stripe_price_id__in=prices).first()
        if prices
        else None
    )
    if matched:
        account.plan_price = matched
        account.price_unmapped = False
    elif prices:
        # Configuration drift: Stripe bills prices this deployment does not map. Keep the
        # current plan so a paying customer is not cut off, but make it visible.
        account.price_unmapped = True
        notes.append("billing.price_unmapped")
    start = obj.get("current_period_start") or (
        items[0].get("current_period_start") if items else None
    )
    end = obj.get("current_period_end") or (items[0].get("current_period_end") if items else None)
    if start:
        account.period_start = datetime.fromtimestamp(start, UTC)
    if end:
        account.period_end = datetime.fromtimestamp(end, UTC)
    account.billing_interval = billing_interval(items)
    trial_end = obj.get("trial_end")
    account.trial_ends_at = datetime.fromtimestamp(trial_end, UTC) if trial_end else None
    return notes


def billing_interval(items):
    """Interval of the base (non-metered) price: monthly or annual."""
    for item in items:
        recurring = (item.get("price") or {}).get("recurring") or {}
        if recurring.get("usage_type") == "metered":
            continue
        interval, count = recurring.get("interval"), int(recurring.get("interval_count") or 1)
        if interval == "month" and count == 1:
            return "monthly"
        if interval == "year" and count == 1:
            return "annual"
        if interval:
            return f"{count}-{interval}"
    return ""


def apply_event(workspace_id, payload, event_id):
    if payload["type"].startswith("checkout.session."):
        metadata = payload["data"]["object"].get("metadata") or {}
        if metadata.get("nemio_credit_topup"):
            from .credits import apply_checkout_event as apply_credit_checkout

            return apply_credit_checkout(workspace_id, payload)
        from apps.marketplace.services import apply_checkout_event

        return apply_checkout_event(workspace_id, payload)
    obj = payload["data"]["object"]
    account = BillingAccount.objects.for_workspace(workspace_id).select_for_update().get()
    if payload["created"] < account.last_event_created:
        return "ignored"
    event_type = payload["type"]
    notes = []
    if event_type.startswith("customer.subscription."):
        if (
            event_type.endswith("deleted")
            and account.subscription_id
            and obj["id"] != account.subscription_id
        ):
            # An older subscription ending after an upgrade replaced it says nothing
            # about the current one.
            return "ignored"
        previous_price = account.plan_price_id
        notes = apply_subscription(account, obj)
        if event_type.endswith("deleted"):
            account.status = "canceled"
        elif (
            event_type.endswith("updated")
            and previous_price
            and (account.plan_price_id != previous_price)
        ):
            from .emails import send_plan_changed

            transaction.on_commit(lambda: send_plan_changed.delay(str(workspace_id)))
        campaign = (obj.get("metadata") or {}).get("promo_campaign")
        if campaign and (obj.get("discount") or obj.get("discounts")):
            from apps.platform_ops.growth import record_redemption

            record_redemption(campaign, workspace_id, obj["id"])
    elif event_type in {"invoice.paid", "invoice.payment_failed"}:
        # Invoices only move the account when they bill the subscription we track and
        # that subscription is still open; a stray or late invoice cannot revive it.
        if (
            not account.subscription_id
            or invoice_subscription(obj) != account.subscription_id
            or account.status in CLOSED_STATUSES
        ):
            return "ignored"
        account.status = "active" if event_type == "invoice.paid" else "past_due"
    account.last_event_created = payload["created"]
    account.save()
    audit(account.workspace, None, "billing.updated", event_id)
    for note in notes:
        audit(account.workspace, None, note, account.id)
        logging.getLogger(__name__).warning(
            "Billing configuration drift", extra={"event_code": note}
        )
    return "processed"


RECONCILED_FIELDS = [
    "status",
    "plan_price_id",
    "price_unmapped",
    "period_start",
    "period_end",
    "billing_interval",
    "trial_ends_at",
]


def reconcile_account(workspace_id, subscription):
    """Correct drift between the webhook-fed account and Stripe's current subscription
    (missed or out-of-order events). Only the tracked subscription is authoritative."""
    with transaction.atomic():
        account = BillingAccount.objects.for_workspace(workspace_id).select_for_update().get()
        if account.subscription_id != subscription.get("id"):
            return False
        before = {field: getattr(account, field) for field in RECONCILED_FIELDS}
        notes = apply_subscription(account, subscription)
        changed = [field for field in RECONCILED_FIELDS if before[field] != getattr(account, field)]
        if not changed:
            return False
        account.save()
        audit(account.workspace, None, "billing.reconciled", account.id)
        for note in notes:
            audit(account.workspace, None, note, account.id)
        return True


@shared_task(ignore_result=True)
def report_usage(workspace_id, record_id):
    if not settings.STRIPE_SECRET_KEY:
        return
    with transaction.atomic():
        record = (
            UsageRecord.objects.for_workspace(workspace_id).select_for_update().get(pk=record_id)
        )
        account = account_for(workspace_id)
        if record.reported_at or not account.customer_id or not account.subscription_id:
            return
        try:
            stripe.billing.MeterEvent.create(
                api_key=settings.STRIPE_SECRET_KEY,
                event_name=settings.STRIPE_METER_EVENT_NAME,
                identifier=str(record.id),
                timestamp=int(record.created_at.timestamp()),
                payload={"stripe_customer_id": account.customer_id, "value": "1"},
                idempotency_key=str(record.id),
            )
        except stripe.StripeError:
            # The identifier makes a later resend safe; back off instead of hammering Stripe.
            record.report_attempts += 1
            record.report_after = timezone.now() + timedelta(
                seconds=min(3600, 30 * 2**record.report_attempts)
            )
            record.save(update_fields=["report_attempts", "report_after"])
            return
        record.reported_at = timezone.now()
        record.save(update_fields=["reported_at"])
