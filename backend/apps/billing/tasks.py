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

from .models import BillingAccount, BillingEvent, BillingJob
from .services import account_for

MAX_REPORT_ATTEMPTS = 10
# Subscription states in which metered usage is billable. Canceled, unpaid or
# incomplete subscriptions must not receive meter events they can never invoice.
METERED_STATUSES = ["active", "past_due"]
CLOSED_STATUSES = {"canceled", "incomplete_expired", "unpaid"}


def reportable_usage():
    # Only usage inside a paid subscription period is metered; trial usage never is.
    return UsageRecord.all_objects.filter(
        status="complete",
        kind="generation",
        reported_at__isnull=True,
        report_attempts__lt=MAX_REPORT_ATTEMPTS,
        workspace__billingaccount__customer_id__isnull=False,
        workspace__billingaccount__subscription_id__gt="",
        workspace__billingaccount__status__in=METERED_STATUSES,
        created_at__gte=F("workspace__billingaccount__period_start"),
    ).filter(Q(report_after__isnull=True) | Q(report_after__lte=timezone.now()))


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
            if job.kind == "portal":
                session = stripe.billing_portal.Session.create(
                    api_key=settings.STRIPE_SECRET_KEY,
                    customer=account.customer_id,
                    return_url=settings.PUBLIC_APP_URL,
                    idempotency_key=str(job.id),
                )
            else:
                prices = settings.STRIPE_PRICES.get(job.plan)
                if not prices or not prices.get("base") or not prices.get("meter"):
                    raise ValueError("price_not_configured")
                session = stripe.checkout.Session.create(
                    api_key=settings.STRIPE_SECRET_KEY,
                    customer=account.customer_id,
                    mode="subscription",
                    line_items=[
                        {"price": prices["base"], "quantity": 1},
                        {"price": prices["meter"]},
                    ],
                    success_url=settings.PUBLIC_APP_URL + "?billing=success",
                    cancel_url=settings.PUBLIC_APP_URL + "?billing=cancelled",
                    subscription_data={
                        "metadata": {"workspace_id": workspace_id, "plan": job.plan}
                    },
                    idempotency_key=str(job.id),
                )
            job.result = json.dumps({"url": session.url})
            job.status = "complete"
        except (stripe.StripeError, ValueError):
            job.status = "failed"
            job.result = json.dumps({"error": "billing_provider_error"})
        job.save()


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
    plan = next(
        (
            name
            for name, configured in settings.STRIPE_PRICES.items()
            if configured.get("base") in prices
        ),
        None,
    )
    if plan:
        account.plan = plan
        limits = settings.PLAN_LIMITS[plan]
        account.seat_limit = limits["seats"]
        account.channel_limit = limits["channels"]
        account.usage_limit = limits["messages"]
    elif prices:
        # Configuration drift: Stripe bills prices this deployment does not map. Keep the
        # current limits so a paying customer is not cut off, but make it visible.
        account.plan = "unmapped"
        notes.append("billing.price_unmapped")
    start = obj.get("current_period_start") or (
        items[0].get("current_period_start") if items else None
    )
    end = obj.get("current_period_end") or (items[0].get("current_period_end") if items else None)
    if start:
        account.period_start = datetime.fromtimestamp(start, UTC)
    if end:
        account.period_end = datetime.fromtimestamp(end, UTC)
    return notes


def apply_event(workspace_id, payload, event_id):
    if payload["type"].startswith("checkout.session."):
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
        notes = apply_subscription(account, obj)
        if event_type.endswith("deleted"):
            account.status = "canceled"
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
    "plan",
    "seat_limit",
    "channel_limit",
    "usage_limit",
    "period_start",
    "period_end",
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
