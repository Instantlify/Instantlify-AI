"""Prepaid AI credits with margin pricing (brief 2.10).

Nemio pays the provider and resells usage at a per-model rate. Every model call, embedding
batch and top-up is one ledger row carrying the amount charged, the real cost and the
balance after it, so the ledger audits itself without replaying history.

Workspaces on `billing_mode="byo_key"` never touch this module: their own provider key is
used and nothing is deducted.
"""

import logging
import re
from decimal import ROUND_HALF_UP, Decimal

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import AICreditBalance, AICreditTransaction, ModelPricingRate

MILLION = Decimal(1_000_000)
CENT = Decimal("0.0001")
log = logging.getLogger(__name__)


class NoPricingRate(Exception):
    pass


def balance_for(workspace_id, *, lock=False):
    from .reseller import effective_billing_workspace_id

    target_id = effective_billing_workspace_id(workspace_id)
    query = AICreditBalance.objects.for_workspace(target_id)
    if lock:
        query = query.select_for_update()
    balance = query.first()
    if balance is None:
        balance, _ = AICreditBalance.objects.for_workspace(target_id).get_or_create(
            workspace_id=target_id
        )
        if lock:
            balance = query.get(pk=balance.pk)
    return balance


def _pattern_matches(pattern, model):
    regex = ".*".join(re.escape(part) for part in pattern.split("%"))
    return re.fullmatch(regex, model, flags=re.IGNORECASE) is not None


def resolve_rate(model):
    """Most specific matching pattern wins (most literal characters); the fallback row
    catches anything unknown so a new or renamed model never bills at zero or crashes."""
    candidates = [
        (len(rate.model_pattern.replace("%", "")), rate)
        for rate in ModelPricingRate.objects.filter(is_fallback_default=False)
        if _pattern_matches(rate.model_pattern, model or "")
    ]
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    fallback = ModelPricingRate.objects.filter(is_fallback_default=True).first()
    if fallback is None:
        raise NoPricingRate(model)
    return fallback


def price(rate, *, tokens_in=0, tokens_out=0, cache_read=0, cache_write=0):
    """(charged, real) in cents, sub-cent precision kept."""

    def total(prefix):
        return (
            Decimal(tokens_in) * getattr(rate, f"{prefix}_input")
            + Decimal(tokens_out) * getattr(rate, f"{prefix}_output")
            + Decimal(cache_read) * getattr(rate, f"{prefix}_cache_read")
            + Decimal(cache_write) * getattr(rate, f"{prefix}_cache_write")
        ) / MILLION

    return (
        total("our").quantize(CENT, rounding=ROUND_HALF_UP),
        total("real").quantize(CENT, rounding=ROUND_HALF_UP),
    )


def has_credit(workspace_id):
    return balance_for(workspace_id).balance_cents > 0


def ensure_credit(workspace_id):
    """True when a model call may proceed. Tries an auto top-up first when the balance is
    empty and the workspace opted in; a failed top-up disables itself and notifies."""
    balance = balance_for(workspace_id)
    if balance.balance_cents > 0:
        return True
    if balance.auto_topup_enabled:
        auto_topup(balance)
        balance.refresh_from_db()
    return balance.balance_cents > 0


@transaction.atomic
def charge(
    workspace_id,
    *,
    key,
    model,
    tokens_in=0,
    tokens_out=0,
    cache_read=0,
    cache_write=0,
    description="",
    usage_record=None,
):
    """Deduct one model call. Idempotent on `key`. Returns the ledger row."""
    existing = AICreditTransaction.objects.for_workspace(workspace_id).filter(key=key).first()
    if existing:
        return existing
    rate = resolve_rate(model)
    charged, real = price(
        rate,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cache_read=cache_read,
        cache_write=cache_write,
    )
    balance = balance_for(workspace_id, lock=True)
    balance.balance_cents -= charged
    balance.save(update_fields=["balance_cents", "updated_at"])
    row = AICreditTransaction.objects.for_workspace(workspace_id).create(
        workspace_id=workspace_id,
        key=key,
        type="usage",
        amount_cents=-charged,
        real_cost_cents=real,
        remaining_balance_cents=balance.balance_cents,
        model=model[:100],
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        rate=rate,
        description=description[:300],
        usage_record=usage_record,
    )
    if balance.auto_topup_enabled and balance.balance_cents < balance.auto_topup_threshold_cents:
        transaction.on_commit(lambda: auto_topup_by_id(workspace_id))
    return row


def auto_topup_by_id(workspace_id):
    auto_topup(balance_for(workspace_id))


def auto_topup(balance):
    """Off-session Stripe charge for the configured amount. One attempt; on failure the
    feature switches itself off and the workspace is told, instead of retrying forever."""
    from apps.tenants.services import audit

    from .services import account_for

    account = account_for(balance.workspace_id)
    if (
        not balance.auto_topup_enabled
        or not balance.payment_method_id
        or not account.customer_id
        or not settings.STRIPE_SECRET_KEY
    ):
        return disable_auto_topup(balance, "auto_topup_unavailable")
    with transaction.atomic():
        locked = balance_for(balance.workspace_id, lock=True)
        locked.topup_attempts += 1
        locked.save(update_fields=["topup_attempts", "updated_at"])
        attempt = locked.topup_attempts
    key = f"autotopup:{balance.pk}:{attempt}"
    try:
        intent = stripe.PaymentIntent.create(
            api_key=settings.STRIPE_SECRET_KEY,
            amount=int(balance.auto_topup_amount_cents),
            currency="usd",
            customer=account.customer_id,
            payment_method=balance.payment_method_id,
            off_session=True,
            confirm=True,
            description="Nemio AI credits auto top-up",
            metadata={"workspace_id": str(balance.workspace_id), "nemio_credit_auto_topup": key},
            idempotency_key=key,
        )
        if intent.status != "succeeded":
            raise stripe.StripeError(f"payment_{intent.status}")
    except stripe.StripeError:
        return disable_auto_topup(balance, "auto_topup_failed")
    credit(
        balance.workspace_id,
        key=key,
        amount_cents=balance.auto_topup_amount_cents,
        type="auto_topup",
        payment_intent=intent.id,
        description="Automatic top-up",
    )
    audit(account.workspace, None, "ai.auto_topup", balance.pk)
    return True


def disable_auto_topup(balance, reason):
    from apps.crm.services import notify
    from apps.tenants.services import audit

    AICreditBalance.objects.for_workspace(balance.workspace_id).filter(pk=balance.pk).update(
        auto_topup_enabled=False, auto_topup_failed_at=timezone.now()
    )
    audit(balance.workspace, None, "ai." + reason, balance.pk)
    log.warning("AI credit auto top-up disabled", extra={"event_code": reason})
    notify(balance.workspace_id)
    from .emails import auto_topup_failed

    workspace_id = balance.workspace_id
    transaction.on_commit(lambda: auto_topup_failed(workspace_id))
    return False


@transaction.atomic
def credit(workspace_id, *, key, amount_cents, type, payment_intent="", description=""):
    """Add credits (top-up, auto top-up, refund or adjustment). Idempotent on `key`."""
    existing = AICreditTransaction.objects.for_workspace(workspace_id).filter(key=key).first()
    if existing:
        return existing
    balance = balance_for(workspace_id, lock=True)
    balance.balance_cents += Decimal(amount_cents)
    balance.save(update_fields=["balance_cents", "updated_at"])
    return AICreditTransaction.objects.for_workspace(workspace_id).create(
        workspace_id=workspace_id,
        key=key,
        type=type,
        amount_cents=Decimal(amount_cents),
        remaining_balance_cents=balance.balance_cents,
        stripe_payment_intent_id=payment_intent[:120],
        description=description[:300],
    )


def grant_signup_credit(workspace_id):
    """The welcome balance that lets a new workspace try the AI before paying.

    Without it `billing_mode="platform_credits"` (the default) starts at zero, so the
    first thing a new signup meets is a card form, and nobody reaches the product they
    came to evaluate. Nemio pays the provider for this, so it is handed out only once
    per workspace, only after the owner confirmed their address (see
    tenants.verification), and only to workspaces that are not an agency's clients:
    a reseller's child balances resolve to the parent, so granting there would pay
    the same agency once per workspace it creates.
    """
    from apps.tenants.models import Workspace

    amount = getattr(settings, "SIGNUP_CREDIT_CENTS", 0)
    if amount <= 0:
        return None
    if Workspace.objects.filter(pk=workspace_id, parent__isnull=False).exists():
        return None
    return credit(
        workspace_id,
        key=f"signup-grant:{workspace_id}",
        amount_cents=amount,
        type="adjustment",
        description="Welcome credit",
    )


def create_topup_session(job, account):
    """Stripe Checkout for a manual top-up. The card is saved for off-session auto
    top-ups; the pending ledger row is the metadata key the webhook routes on."""
    pending = AICreditTransaction.objects.for_workspace(job.workspace_id).create(
        workspace_id=job.workspace_id,
        key=f"topup:{job.id}",
        type="topup",
        status="pending",
        amount_cents=Decimal(job.amount_cents),
        remaining_balance_cents=balance_for(job.workspace_id).balance_cents,
        description="AI credits top-up",
    )
    return stripe.checkout.Session.create(
        api_key=settings.STRIPE_SECRET_KEY,
        customer=account.customer_id,
        mode="payment",
        line_items=[
            {
                "quantity": 1,
                "price_data": {
                    "currency": "usd",
                    "unit_amount": int(job.amount_cents),
                    "product_data": {"name": "Nemio AI credits"},
                },
            }
        ],
        payment_intent_data={
            "setup_future_usage": "off_session",
            "metadata": {"workspace_id": str(job.workspace_id)},
        },
        metadata={"nemio_credit_topup": str(pending.pk), "workspace": str(job.workspace_id)},
        success_url=settings.PUBLIC_APP_URL + "?credits=success",
        cancel_url=settings.PUBLIC_APP_URL + "?credits=cancelled",
        idempotency_key=str(job.id),
    )


def apply_checkout_event(workspace_id, payload):
    """Platform webhook for top-up checkouts (routed by `nemio_credit_topup` metadata)."""
    session = payload["data"]["object"]
    event_type = payload["type"]
    pending_id = (session.get("metadata") or {}).get("nemio_credit_topup")
    with transaction.atomic():
        pending = (
            AICreditTransaction.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=pending_id, type="topup")
            .first()
        )
        if pending is None:
            return "ignored"
        if (
            event_type
            in {
                "checkout.session.completed",
                "checkout.session.async_payment_succeeded",
            }
            and session.get("payment_status") == "paid"
        ):
            if pending.status == "pending":
                amount = session.get("amount_total") or pending.amount_cents
                balance = balance_for(workspace_id, lock=True)
                balance.balance_cents += Decimal(amount)
                balance.save(update_fields=["balance_cents", "updated_at"])
                pending.status = "complete"
                pending.amount_cents = Decimal(amount)
                pending.remaining_balance_cents = balance.balance_cents
                pending.stripe_payment_intent_id = str(session.get("payment_intent") or "")[:120]
                pending.save()
                remember_payment_method(balance, pending.stripe_payment_intent_id)
        elif event_type in {"checkout.session.expired", "checkout.session.async_payment_failed"}:
            if pending.status == "pending":
                pending.status = "expired" if event_type.endswith("expired") else "failed"
                pending.save(update_fields=["status"])
    return "processed"


def remember_payment_method(balance, payment_intent_id):
    """Best effort: keep the card from a manual top-up for future auto top-ups."""
    if not payment_intent_id or not settings.STRIPE_SECRET_KEY:
        return
    try:
        intent = stripe.PaymentIntent.retrieve(
            payment_intent_id, api_key=settings.STRIPE_SECRET_KEY
        )
        method = intent.get("payment_method") if isinstance(intent, dict) else intent.payment_method
    except stripe.StripeError:
        return
    if method:
        AICreditBalance.objects.for_workspace(balance.workspace_id).filter(pk=balance.pk).update(
            payment_method_id=str(method)[:100]
        )
