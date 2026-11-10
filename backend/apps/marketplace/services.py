"""Paid template installs on Stripe Connect.

Instantlify owns checkout (merchant of record). Authors onboard a Connect *recipient*
account (Accounts v2, express dashboard); buyers pay a destination charge on the
platform account and the author's share moves automatically, less the platform
fee. Capability status is re-read from Stripe before any charge references an
author, so a restricted account never receives a transfer it cannot accept."""

import math
from datetime import timedelta

import stripe
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from stripe import StripeClient

from apps.channels.transport import ProviderError
from apps.tenants.services import audit

from .models import SellerAccount, Template, TemplateInstall, TemplatePurchase

CAPABILITY_STALE_AFTER = timedelta(hours=1)
CHECKOUT_TTL = timedelta(hours=25)


def stripe_client():
    if not settings.STRIPE_SECRET_KEY:
        raise ValueError("stripe_not_configured")
    return StripeClient(settings.STRIPE_SECRET_KEY)


def fee_for(amount_cents):
    """Platform share, rounded up so a 1-cent template never transfers more than it took."""
    percent = max(0, min(100, settings.MARKETPLACE_FEE_PERCENT))
    return min(amount_cents, math.ceil(amount_cents * percent / 100))


def _templates_url(workspace_id, query):
    return f"{settings.PUBLIC_APP_URL}/w/{workspace_id}/templates?{query}"


def apply_account(seller, account):
    """Record the v2 capability status; anything unreadable counts as not active."""
    status = "pending"
    try:
        status = account.configuration.recipient.capabilities.stripe_balance.stripe_transfers.status
    except AttributeError:
        pass
    requirements = getattr(account, "requirements", None)
    entries = getattr(requirements, "entries", None) or []
    seller.transfers_status = str(status)[:20]
    seller.requirements_due = bool(entries)
    seller.checked_at = timezone.now()
    seller.save(update_fields=["transfers_status", "requirements_due", "checked_at"])
    return seller


def can_receive(seller):
    return bool(seller) and seller.transfers_status == "active"


@transaction.atomic
def ensure_seller(workspace, user, country="us"):
    seller = SellerAccount.objects.for_workspace(workspace).select_for_update().first()
    if seller:
        return seller
    client = stripe_client()
    try:
        account = client.v2.core.accounts.create(
            {
                "display_name": workspace.name[:100],
                "contact_email": getattr(user, "email", "") or None,
                "dashboard": "express",
                "identity": {"country": country},
                "defaults": {
                    "responsibilities": {
                        "fees_collector": "application",
                        "losses_collector": "application",
                    }
                },
                "configuration": {
                    "recipient": {
                        "capabilities": {
                            "stripe_balance": {"stripe_transfers": {"requested": True}}
                        }
                    }
                },
                "metadata": {"workspace_id": str(workspace.pk)},
                "include": ["configuration.recipient", "requirements"],
            },
            {"idempotency_key": f"nemio-seller:{workspace.pk}"},
        )
    except stripe.StripeError:
        raise ProviderError("payment_provider_error") from None
    seller = SellerAccount.objects.for_workspace(workspace).create(
        workspace=workspace, stripe_account_id=account.id, country=country
    )
    apply_account(seller, account)
    audit(workspace, user, "marketplace.seller_created", seller.id)
    return seller


def onboarding_link(seller):
    """Single-use Stripe-hosted onboarding (or requirements update) URL."""
    client = stripe_client()
    try:
        link = client.v2.core.account_links.create(
            {
                "account": seller.stripe_account_id,
                "use_case": {
                    "type": "account_onboarding",
                    "account_onboarding": {
                        "configurations": ["recipient"],
                        "refresh_url": _templates_url(seller.workspace_id, "payouts=refresh"),
                        "return_url": _templates_url(seller.workspace_id, "payouts=return"),
                    },
                },
            }
        )
    except stripe.StripeError:
        raise ProviderError("payment_provider_error") from None
    return link.url


def sync_seller(seller):
    client = stripe_client()
    try:
        account = client.v2.core.accounts.retrieve(
            seller.stripe_account_id, {"include": ["configuration.recipient", "requirements"]}
        )
    except stripe.StripeError:
        raise ProviderError("payment_provider_error") from None
    return apply_account(seller, account)


def dashboard_link(seller):
    """Login link into the express dashboard (balance, payouts, tax forms)."""
    client = stripe_client()
    try:
        return client.accounts.login_links.create(seller.stripe_account_id).url
    except stripe.StripeError:
        raise ProviderError("payment_provider_error") from None


def seller_for_template(template):
    # Cross-tenant read by design: the buyer's checkout must name the author's account.
    seller = SellerAccount.all_objects.filter(workspace_id=template.workspace_id).first()
    if seller and (
        not seller.checked_at or timezone.now() - seller.checked_at > CAPABILITY_STALE_AFTER
    ):
        seller = sync_seller(seller)
    return seller


def start_purchase(workspace, user, template, key):
    """Create (or return) the checkout for this buyer + template. Idempotent on `key`,
    and a template already paid for is returned instead of charged again."""
    from apps.platform_ops.security import assert_enabled

    assert_enabled(workspace.pk, "marketplace", "integration:stripe")
    purchases = TemplatePurchase.objects.for_workspace(workspace)
    existing = purchases.filter(idempotency_key=key).first()
    if existing:
        return existing
    owned = purchases.filter(template_id=template.pk, status__in=["paid", "installed"]).first()
    if owned:
        return owned
    # Outside the checkout transaction so a refreshed (e.g. restricted) status persists
    # even when the purchase is refused.
    seller = seller_for_template(template)
    if not can_receive(seller):
        raise ValueError("seller_unavailable")
    return _create_checkout(workspace, user, template, key, seller)


@transaction.atomic
def _create_checkout(workspace, user, template, key, seller):
    client = stripe_client()
    amount = template.price_cents
    purchase = TemplatePurchase.objects.for_workspace(workspace).create(
        workspace=workspace,
        template_id=template.pk,
        seller_workspace_id=template.workspace_id,
        title=template.title,
        amount_cents=amount,
        fee_cents=fee_for(amount),
        currency="usd",
        idempotency_key=key,
    )
    metadata = {"nemio_template_purchase": str(purchase.pk), "workspace": str(workspace.pk)}
    try:
        session = client.checkout.sessions.create(
            {
                "mode": "payment",
                "line_items": [
                    {
                        "price_data": {
                            "currency": purchase.currency,
                            "unit_amount": amount,
                            "product_data": {"name": f"Template: {template.title}"[:120]},
                        },
                        "quantity": 1,
                    }
                ],
                "payment_intent_data": {
                    "application_fee_amount": purchase.fee_cents,
                    "transfer_data": {"destination": seller.stripe_account_id},
                    "metadata": metadata,
                },
                "metadata": metadata,
                "success_url": _templates_url(workspace.pk, f"purchase={purchase.pk}"),
                "cancel_url": _templates_url(workspace.pk, f"purchase={purchase.pk}&cancelled=1"),
            },
            {"idempotency_key": f"nemio-template:{purchase.pk}"},
        )
    except stripe.StripeError:
        raise ProviderError("payment_provider_error") from None
    purchase.checkout_session_id = session.id
    purchase.checkout_url = session.url or ""
    purchase.save(update_fields=["checkout_session_id", "checkout_url"])
    audit(workspace, user, "template.purchase_started", purchase.id)
    return purchase


def install_purchase(purchase, actor=None):
    """Turn a paid purchase into a draft automation. Safe to call again after a failure."""
    from django.core.exceptions import ValidationError as DjangoValidationError
    from rest_framework.exceptions import ValidationError

    from apps.automations.templates import FORMAT, VERSION, import_automation

    if purchase.status == "installed" and purchase.automation_id:
        return purchase.automation
    if purchase.status not in {"paid", "installed"}:
        raise ValueError("purchase_not_paid")
    # The graph is taken from the template row even if the author unlisted it since:
    # the buyer paid for what was listed at the time.
    template = Template.all_objects.filter(pk=purchase.template_id).first()
    if not template:
        raise ValueError("template_missing")
    try:
        automation = import_automation(
            purchase.workspace,
            {"format": FORMAT, "version": VERSION, "name": template.title, "graph": template.graph},
            actor,
            installed_from=template.pk,
        )
    except (ValidationError, DjangoValidationError, KeyError, TypeError):
        audit(purchase.workspace, actor, "template.install_failed", purchase.id)
        raise ValueError("template_invalid") from None
    TemplateInstall.objects.for_workspace(purchase.workspace_id).create(
        workspace=purchase.workspace, template_id=template.pk, automation=automation
    )
    Template.all_objects.filter(pk=template.pk).update(install_count=F("install_count") + 1)
    purchase.automation = automation
    purchase.status = "installed"
    purchase.save(update_fields=["automation", "status"])
    audit(purchase.workspace, actor, "template.installed", purchase.id)
    return automation


@transaction.atomic
def mark_purchase_paid(workspace_id, session_id, amount_cents=None):
    purchase = (
        TemplatePurchase.objects.for_workspace(workspace_id)
        .select_for_update()
        .filter(checkout_session_id=session_id)
        .first()
    )
    if not purchase or purchase.status in {"paid", "installed"}:
        return purchase
    purchase.status = "paid"
    purchase.paid_at = timezone.now()
    if amount_cents:
        purchase.amount_cents = amount_cents
    purchase.save(update_fields=["status", "paid_at", "amount_cents"])
    audit(purchase.workspace, None, "template.purchase_paid", purchase.id)
    try:
        install_purchase(purchase)
    except ValueError:
        # Paid but not installable right now: the buyer can retry from the app.
        pass
    return purchase


@transaction.atomic
def mark_purchase_closed(workspace_id, session_id, status):
    TemplatePurchase.objects.for_workspace(workspace_id).filter(
        checkout_session_id=session_id, status="pending"
    ).update(status=status)


def apply_checkout_event(workspace_id, payload):
    """Platform Stripe webhook events for template checkouts (routed by metadata)."""
    session = payload["data"]["object"]
    event_type = payload["type"]
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        if session.get("payment_status") == "paid":
            mark_purchase_paid(workspace_id, session["id"], session.get("amount_total"))
    elif event_type == "checkout.session.expired":
        mark_purchase_closed(workspace_id, session["id"], "expired")
    elif event_type == "checkout.session.async_payment_failed":
        mark_purchase_closed(workspace_id, session["id"], "failed")
    return "processed"


def sync_purchase(purchase):
    """Fallback when the webhook has not arrived (local dev, delayed delivery)."""
    if purchase.status != "pending" or not purchase.checkout_session_id:
        return purchase
    client = stripe_client()
    try:
        session = client.checkout.sessions.retrieve(purchase.checkout_session_id)
    except stripe.StripeError:
        raise ProviderError("payment_provider_error") from None
    if session.payment_status == "paid":
        return mark_purchase_paid(purchase.workspace_id, session.id, session.amount_total)
    if session.status == "expired":
        mark_purchase_closed(purchase.workspace_id, session.id, "expired")
        purchase.refresh_from_db()
    return purchase
