import stripe
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.agents.models import UsageRecord
from apps.billing.models import BillingAccount
from apps.billing.stripe_data import stripe_data
from apps.billing.tasks import reconcile_account

from .metrics import monthly_amounts
from .models import SubscriptionSnapshot
from .uptime import probe_uptime  # noqa: F401  (registers the beat task)


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
            subscription = stripe_data(subscription)
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
                            "overage": max(0, used - (account.usage_limit or used)),
                        },
                    )
        except (stripe.StripeError, ValueError, KeyError, TypeError):
            failures += 1
    cache.set(
        "ops:billing_sync",
        f"Last sync {timezone.now().isoformat()}; failed accounts: {failures}",
        90000,
    )


@shared_task(ignore_result=True, soft_time_limit=100, time_limit=120)
def classify_connection(connection_id):
    """Derive a marketing segment for one connected account from its public profile.

    Runs on every reconnect, because the bio it reads is the thing that changes.
    Producing no row is a valid outcome: a thin bio genuinely does not say what a
    business does, and a forced guess pollutes every segment count downstream.
    """
    from apps.channels.models import ChannelConnection
    from apps.tenants.models import Membership

    from .intelligence import classify_account
    from .models import SegmentCategory, UserSegment

    connection = ChannelConnection.all_objects.filter(pk=connection_id).first()
    if not connection:
        return
    owner = (
        Membership.all_objects.filter(workspace_id=connection.workspace_id, role="owner")
        .select_related("user")
        .first()
    )
    if not owner:
        return
    categories = list(SegmentCategory.objects.filter(is_active=True).values_list("name", flat=True))
    profile = connection.profile or {}
    handle = connection.display_name or connection.external_account_id
    verdict = classify_account(
        handle=handle,
        display_name=profile.get("name", ""),
        bio=profile.get("biography", ""),
        site_text=profile.get("website", ""),
        categories=categories,
    )
    # Segments are re-derived, not accumulated: drop this account's previous verdict
    # so a rebranded account does not keep its stale category forever.
    UserSegment.objects.filter(user=owner.user, source_account=handle).delete()
    if not verdict:
        return
    is_primary = not UserSegment.objects.filter(user=owner.user, is_primary=True).exists()
    UserSegment.objects.create(
        user=owner.user,
        workspace_id=connection.workspace_id,
        connection_id=connection.pk,
        source_account=handle,
        category=verdict["category"],
        confidence=verdict["confidence"],
        evidence=verdict["evidence"],
        is_primary=is_primary,
    )


@shared_task(ignore_result=True, soft_time_limit=280, time_limit=300)
def embed_platform_knowledge():
    """Re-embed the platform support bot's knowledge base. Explicitly manual: batching
    this behind an operator action beats re-embedding on every keystroke."""
    from .intelligence import embed
    from .models import PlatformKnowledgeDocument, PlatformKnowledgeSection

    sections = list(PlatformKnowledgeSection.objects.select_related("document"))
    if not sections:
        return 0
    texts = [f"{section.title}\n{section.body_markdown}" for section in sections]
    vectors, _ = embed(texts)
    now = timezone.now()
    for section, vector in zip(sections, vectors, strict=False):
        section.embedding = vector
        section.embedded_at = now
        section.save(update_fields=["embedding", "embedded_at"])
    PlatformKnowledgeDocument.objects.update(embedded_at=now)
    return len(sections)


@shared_task(ignore_result=True, soft_time_limit=280, time_limit=300)
def scan_billing(run_id):
    """On-demand reconciliation of local subscription state against live Stripe.

    Deliberately never scheduled: it spends real API calls, and it answers a question
    a person asked. Two findings, both classic Stripe-integration failure modes —
    a local status that disagrees with Stripe's, and a trial with no card attached
    that therefore cannot convert when it ends.
    """
    from apps.billing.models import BillingAccount

    from .models import BillingAuditRun

    run = BillingAuditRun.objects.filter(pk=run_id).first()
    if not run:
        return
    stale, cardless, checked = [], [], 0
    accounts = BillingAccount.all_objects.exclude(subscription_id="").select_related("workspace")
    try:
        if not settings.STRIPE_SECRET_KEY:
            raise ValueError("Stripe is not configured.")
        for account in accounts.iterator():
            checked += 1
            try:
                subscription = stripe.Subscription.retrieve(
                    account.subscription_id,
                    api_key=settings.STRIPE_SECRET_KEY,
                    expand=["default_payment_method"],
                )
                subscription = stripe_data(subscription)
            except stripe.StripeError as exc:
                stale.append(
                    {
                        "workspace": account.workspace.name,
                        "workspace_id": str(account.workspace_id),
                        "subscription": account.subscription_id,
                        "local": account.status,
                        "stripe": "unreachable",
                        "detail": str(exc)[:120],
                    }
                )
                continue
            if subscription["status"] != account.status:
                stale.append(
                    {
                        "workspace": account.workspace.name,
                        "workspace_id": str(account.workspace_id),
                        "subscription": account.subscription_id,
                        "local": account.status,
                        "stripe": subscription["status"],
                        "detail": "Local status disagrees with Stripe.",
                    }
                )
            has_card = bool(
                subscription.get("default_payment_method")
                or (subscription.get("customer") or {}).get("invoice_settings", {})
                if isinstance(subscription.get("customer"), dict)
                else subscription.get("default_payment_method")
            )
            if subscription["status"] == "trialing" and not has_card:
                cardless.append(
                    {
                        "workspace": account.workspace.name,
                        "workspace_id": str(account.workspace_id),
                        "subscription": account.subscription_id,
                        "trial_ends": str(account.trial_ends_at or ""),
                    }
                )
    except (ValueError, stripe.StripeError) as exc:
        run.status = "failed"
        run.error = str(exc)[:300]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        return
    run.status = "complete"
    run.checked = checked
    run.findings = {"stale": stale, "cardless": cardless}
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "checked", "findings", "finished_at"])
