"""In-chat payments on the tenant's own Stripe account (BYO keys, per-workspace webhook)."""

import json

import stripe
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.channels.transport import ProviderError
from apps.crm.models import IntegrationConfig
from apps.tenants.services import audit

from .models import Offer, Payment


def stripe_integration(workspace_id):
    integration = (
        IntegrationConfig.objects.for_workspace(workspace_id)
        .filter(provider="stripe", enabled=True)
        .first()
    )
    if not integration:
        raise ValueError("payments_not_connected")
    if integration.is_test and settings.CHANNEL_ADAPTER_MODE != "fake":
        raise ValueError("test_payments_disabled")
    return integration


@transaction.atomic
def create_checkout(offer, conversation, key):
    """Create (or return) the checkout for this intent. Amounts come from the Offer row."""
    existing = Payment.objects.for_workspace(offer.workspace_id).filter(idempotency_key=key).first()
    if existing:
        return existing
    if not offer.active:
        raise ValueError("offer_inactive")
    integration = stripe_integration(offer.workspace_id)
    lead = conversation.identity.lead
    if lead.opted_out:
        raise ValueError("lead_opted_out")
    payment = Payment.objects.for_workspace(offer.workspace_id).create(
        workspace_id=offer.workspace_id,
        offer=offer,
        conversation=conversation,
        lead=lead,
        amount_cents=offer.amount_cents,
        currency=offer.currency,
        idempotency_key=key,
    )
    if integration.is_test:
        payment.checkout_session_id = f"cs_test_{payment.pk.hex[:16]}"
        payment.checkout_url = f"{settings.PUBLIC_APP_URL}/pay/test/{payment.pk}/"
    else:
        credentials = json.loads(integration.credentials)
        try:
            session = stripe.checkout.Session.create(
                api_key=credentials["secret_key"],
                mode="payment",
                line_items=[
                    {
                        "price_data": {
                            "currency": offer.currency,
                            "unit_amount": offer.amount_cents,
                            "product_data": {"name": offer.name[:120]},
                        },
                        "quantity": 1,
                    }
                ],
                customer_email=lead.email or None,
                success_url=integration.options.get("success_url")
                or settings.PUBLIC_APP_URL + "/pay/thanks/",
                cancel_url=integration.options.get("cancel_url")
                or settings.PUBLIC_APP_URL + "/pay/cancelled/",
                metadata={"nemio_payment": str(payment.pk), "workspace": str(offer.workspace_id)},
                idempotency_key=f"nemio:{payment.pk}",
            )
        except (stripe.StripeError, KeyError):
            raise ProviderError("payment_provider_error") from None
        payment.checkout_session_id = session.id
        payment.checkout_url = session.url
    payment.save()
    audit(payment.workspace, None, "payment.created", payment.id)
    return payment


@transaction.atomic
def mark_paid(workspace_id, session_id, amount_cents=None):
    payment = (
        Payment.objects.for_workspace(workspace_id)
        .select_for_update()
        .select_related("conversation__identity__connection", "lead")
        .filter(checkout_session_id=session_id)
        .first()
    )
    if not payment or payment.status == "paid":
        return payment
    payment.status = "paid"
    payment.paid_at = timezone.now()
    if amount_cents:
        payment.amount_cents = amount_cents
    payment.save()
    lead = payment.lead
    lead.stage = "won"
    lead.save(update_fields=["stage"])
    audit(payment.workspace, None, "payment.paid", payment.id)
    from apps.analytics.services import attribution, record
    from apps.public_api.services import emit

    record(
        workspace_id,
        "paid",
        key=f"paid:{payment.id}",
        provider=payment.conversation.identity.connection.provider,
        lead_id=lead.pk,
        conversation_id=payment.conversation_id,
        amount_cents=payment.amount_cents,
        **attribution(payment.conversation),
    )
    emit(
        workspace_id,
        "payment.paid",
        {
            "payment_id": str(payment.id),
            "lead_id": str(lead.pk),
            "amount_cents": payment.amount_cents,
            "currency": payment.currency,
            "offer": payment.offer.name,
        },
    )
    return payment


@csrf_exempt
def tenant_stripe_webhook(request, workspace_id):
    """Each workspace registers this URL in its own Stripe dashboard."""
    if request.method != "POST":
        return HttpResponse(status=405)
    integration = (
        IntegrationConfig.objects.for_workspace(workspace_id)
        .filter(provider="stripe", enabled=True, is_test=False)
        .first()
    )
    if not integration:
        return HttpResponse(status=404)
    credentials = json.loads(integration.credentials)
    try:
        event = stripe.Webhook.construct_event(
            request.body,
            request.headers.get("Stripe-Signature", ""),
            credentials.get("webhook_secret", ""),
        )
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponse(status=400)
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        if session.get("payment_status") == "paid":
            mark_paid(workspace_id, session["id"], session.get("amount_total"))
    return HttpResponse(status=200)


def offers_for(config):
    return list(Offer.objects.for_workspace(config.workspace_id).filter(active=True)[:20])
