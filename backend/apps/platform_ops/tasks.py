import stripe
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.agents.models import UsageRecord
from apps.billing.models import BillingAccount
from apps.billing.tasks import reconcile_account

from .metrics import monthly_amounts
from .models import SubscriptionSnapshot


@shared_task(ignore_result=True, soft_time_limit=100, time_limit=120)
def sync_subscriptions():
    if not settings.STRIPE_SECRET_KEY:
        cache.set("ops:billing_sync", "Stripe not configured", 90000)
        return
    failures = 0
    for account in BillingAccount.all_objects.exclude(subscription_id="").iterator():
        try:
            subscription = stripe.Subscription.retrieve(
                account.subscription_id, api_key=settings.STRIPE_SECRET_KEY
            )
            if reconcile_account(account.workspace_id, subscription):
                account.refresh_from_db()
            amounts = monthly_amounts(subscription)
            used = (
                UsageRecord.objects.for_workspace(account.workspace_id)
                .filter(kind="generation", created_at__gte=account.period_start)
                .count()
            )
            with transaction.atomic():
                for currency, monthly in amounts.items():
                    SubscriptionSnapshot.objects.update_or_create(
                        workspace_id=account.workspace_id,
                        day=timezone.now().date(),
                        currency=currency,
                        defaults={
                            "monthly_cents": monthly,
                            "status": subscription["status"],
                            "overage": max(0, used - account.usage_limit),
                        },
                    )
        except (stripe.StripeError, ValueError, KeyError, TypeError):
            failures += 1
    cache.set(
        "ops:billing_sync",
        f"Last sync {timezone.now().isoformat()}; failed accounts: {failures}",
        90000,
    )
