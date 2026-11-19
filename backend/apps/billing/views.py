import json

import stripe
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.models import UsageRecord
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import (
    AICreditBalance,
    AICreditTransaction,
    BillingAccount,
    BillingEvent,
    BillingJob,
    Offer,
    Payment,
    Plan,
)
from .services import account_for
from .stripe_data import stripe_data


@csrf_exempt
def stripe_webhook(request):
    if request.method != "POST" or not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse(status=400)
    try:
        event = stripe.Webhook.construct_event(
            request.body,
            request.headers.get("Stripe-Signature", ""),
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponse(status=400)
    event = stripe_data(event)
    workspace_id = event_workspace(event)
    if workspace_id:
        with transaction.atomic():
            BillingEvent.objects.for_workspace(workspace_id).get_or_create(
                event_id=event["id"],
                defaults={"workspace_id": workspace_id, "payload": request.body.decode()},
            )
    return HttpResponse(status=200)


def event_workspace(event):
    """Route a platform-account event to the tenant it concerns: subscription events
    by Stripe customer, marketplace checkouts by the purchase metadata we set.
    Anything else is acknowledged and dropped."""
    obj = event["data"]["object"]
    if event["type"].startswith("checkout.session."):
        metadata = obj.get("metadata") or {}
        topup_id = metadata.get("instantlify_credit_topup")
        if topup_id:
            try:
                pending = AICreditTransaction.all_objects.filter(pk=topup_id).first()
            except (ValueError, ValidationError):
                return None
            if pending and str(pending.workspace_id) == metadata.get("workspace"):
                return pending.workspace_id
            return None
        purchase_id = metadata.get("instantlify_template_purchase")
        if purchase_id:
            from apps.marketplace.models import TemplatePurchase

            try:
                purchase = TemplatePurchase.all_objects.filter(pk=purchase_id).first()
            except (ValueError, ValidationError):
                return None
            if purchase and str(purchase.workspace_id) == metadata.get("workspace"):
                return purchase.workspace_id
        return None
    customer = obj.get("customer")
    account = BillingAccount.all_objects.filter(customer_id=customer).first() if customer else None
    return account.workspace_id if account else None


def plan_catalog():
    """Public tiers with both prices: one source of truth for the pricing page, the
    Payments page and the in-app upgrade modal."""
    return [
        {
            "slug": plan.slug,
            "name": plan.name,
            "is_featured": plan.is_featured,
            "limits": plan.limits.as_dict(),
            "prices": [
                {
                    "interval": price.billing_interval,
                    "price_cents": price.price_cents,
                    "configured": bool(price.stripe_price_id),
                }
                for price in plan.prices.all()
            ],
        }
        for plan in Plan.objects.filter(is_active=True, is_custom=False).prefetch_related("prices")
    ]


class PublicPlansView(APIView):
    """Anonymous catalog for the marketing pricing page."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"plans": plan_catalog(), "trial_days": settings.STRIPE_TRIAL_DAYS})


class BillingView(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"], allow_pending=True)
        account = account_for(workspace_id)
        usage = UsageRecord.objects.for_workspace(workspace_id).filter(
            created_at__gte=account.period_start, kind="generation"
        )
        limits = account.limits
        catalog = plan_catalog()
        return Response(
            {
                "plan": account.plan,
                "interval": account.billing_interval,
                "status": account.status,
                "trial_ends_at": account.trial_ends_at,
                "used": usage.count(),
                "usage_limit": limits.max_ai_messages,
                "seat_limit": limits.team_seats,
                "channel_limit": limits.max_instagram_accounts,
                "limits": limits.as_dict(),
                "stripe_configured": bool(settings.STRIPE_SECRET_KEY),
                "period_start": account.period_start,
                "trial_days": settings.STRIPE_TRIAL_DAYS,
                # Compatibility shape for older clients.
                "plans": {
                    plan["slug"]: {
                        "seats": plan["limits"]["team_seats"],
                        "channels": plan["limits"]["max_instagram_accounts"],
                        "messages": plan["limits"]["max_ai_messages"],
                    }
                    for plan in catalog
                    if plan["slug"] != settings.DEFAULT_PLAN_SLUG
                },
                "catalog": catalog,
            }
        )

    def post(self, request, workspace_id):
        kind = request.data.get("kind", "checkout")
        member = workspace_membership(
            request, workspace_id, ["owner"], allow_pending=kind == "checkout"
        )
        plan = request.data.get("plan", "")
        interval = request.data.get("interval", "monthly")
        key = request.headers.get("Idempotency-Key", "")
        sellable = Plan.objects.filter(
            slug=plan, is_active=True, prices__billing_interval=interval
        ).exists()
        try:
            amount = int(request.data.get("amount_cents", 0) or 0)
        except (TypeError, ValueError):
            amount = 0
        valid_topup = (
            settings.AI_CREDIT_MIN_TOPUP_CENTS <= amount <= settings.AI_CREDIT_MAX_TOPUP_CENTS
        )
        if (
            kind not in {"checkout", "portal", "credits"}
            or interval not in {"monthly", "annual"}
            or (kind == "checkout" and not sellable)
            or (member.workspace.checkout_pending and plan == "free")
            or (kind == "credits" and not valid_topup)
            or not 1 <= len(key) <= 100
        ):
            raise serializers.ValidationError("Supply a valid plan, action and Idempotency-Key.")
        job, _ = BillingJob.objects.for_workspace(workspace_id).get_or_create(
            request_key=key,
            defaults={
                "workspace_id": workspace_id,
                "kind": kind,
                "plan": plan,
                "interval": interval,
                "amount_cents": amount if kind == "credits" else 0,
                "return_to": "onboarding" if request.data.get("return_to") == "onboarding" else "",
            },
        )
        return Response(
            {"id": job.id, "status": job.status, "result": json.loads(job.result)}, status=202
        )


class CreditsView(APIView):
    """Prepaid AI credit balance, auto top-up settings and the recent ledger."""

    def get(self, request, workspace_id):
        from apps.agents.models import AgentConfig

        from .credits import balance_for, resolve_rate

        workspace_membership(request, workspace_id, ["owner", "admin"])
        balance = balance_for(workspace_id)
        config = AgentConfig.objects.for_workspace(workspace_id).first()
        rate = None
        if config:
            try:
                matched = resolve_rate(config.model)
                rate = {
                    "model": config.model,
                    "input_per_million_cents": matched.our_input,
                    "output_per_million_cents": matched.our_output,
                }
            except Exception:  # NoPricingRate: the console has not configured a fallback
                rate = None
        return Response(
            {
                "billing_mode": config.billing_mode if config else "platform_credits",
                "balance_cents": balance.balance_cents,
                "auto_topup_enabled": balance.auto_topup_enabled,
                "auto_topup_threshold_cents": balance.auto_topup_threshold_cents,
                "auto_topup_amount_cents": balance.auto_topup_amount_cents,
                "has_payment_method": bool(balance.payment_method_id),
                "auto_topup_failed_at": balance.auto_topup_failed_at,
                "topup_options": settings.AI_CREDIT_TOPUP_OPTIONS,
                "stripe_configured": bool(settings.STRIPE_SECRET_KEY),
                "rate": rate,
                "transactions": list(
                    AICreditTransaction.objects.for_workspace(workspace_id).values(
                        "id",
                        "type",
                        "status",
                        "amount_cents",
                        "real_cost_cents",
                        "remaining_balance_cents",
                        "model",
                        "tokens_in",
                        "tokens_out",
                        "description",
                        "created_at",
                    )[:50]
                ),
            }
        )

    def patch(self, request, workspace_id):
        from .credits import balance_for

        member = workspace_membership(request, workspace_id, ["owner"])
        balance = balance_for(workspace_id)
        enabled = bool(request.data.get("auto_topup_enabled", balance.auto_topup_enabled))
        try:
            threshold = int(
                request.data.get("auto_topup_threshold_cents", balance.auto_topup_threshold_cents)
            )
            amount = int(
                request.data.get("auto_topup_amount_cents", balance.auto_topup_amount_cents)
            )
        except (TypeError, ValueError):
            raise serializers.ValidationError("Amounts must be whole cents.") from None
        if not 0 <= threshold <= settings.AI_CREDIT_MAX_TOPUP_CENTS:
            raise serializers.ValidationError("Choose a threshold up to the top-up maximum.")
        if not settings.AI_CREDIT_MIN_TOPUP_CENTS <= amount <= settings.AI_CREDIT_MAX_TOPUP_CENTS:
            raise serializers.ValidationError("Choose a top-up amount within the allowed range.")
        if enabled and not balance.payment_method_id:
            raise serializers.ValidationError(
                "Make one manual top-up first so a card is on file for automatic top-ups."
            )
        AICreditBalance.objects.for_workspace(workspace_id).filter(pk=balance.pk).update(
            auto_topup_enabled=enabled,
            auto_topup_threshold_cents=threshold,
            auto_topup_amount_cents=amount,
            auto_topup_failed_at=None if enabled else balance.auto_topup_failed_at,
        )
        audit(member.workspace, request.user, "ai.auto_topup_configured", balance.pk)
        return self.get(request, workspace_id)


class OfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = ["id", "name", "description", "amount_cents", "currency", "active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_amount_cents(self, value):
        if not 50 <= value <= 100_000_00:
            raise serializers.ValidationError("Amount must be between 0.50 and 100,000.")
        return value

    def validate_currency(self, value):
        value = value.lower()
        if value not in {"usd", "eur", "gbp", "cad", "aud", "nzd", "chf", "sek", "nok", "dkk"}:
            raise serializers.ValidationError("Unsupported currency.")
        return value


class OfferList(generics.ListCreateAPIView):
    serializer_class = OfferSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"])
        return Offer.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_create(self, serializer):
        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        if Offer.objects.for_workspace(member.workspace_id).count() >= 50:
            raise serializers.ValidationError("Offer limit reached (50).")
        item = serializer.save(workspace=member.workspace)
        audit(member.workspace, self.request.user, "offer.created", item.id)


class OfferDetail(generics.RetrieveUpdateAPIView):
    serializer_class = OfferSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        roles = None if self.request.method == "GET" else ["owner", "admin"]
        workspace_membership(self.request, self.kwargs["workspace_id"], roles)
        return Offer.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_update(self, serializer):
        item = serializer.save()
        audit(item.workspace, self.request.user, "offer.updated", item.id)


class PaymentList(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        return Response(
            list(
                Payment.objects.for_workspace(workspace_id).values(
                    "id",
                    "offer_id",
                    "conversation_id",
                    "lead_id",
                    "amount_cents",
                    "currency",
                    "status",
                    "paid_at",
                    "created_at",
                )[:100]
            )
        )


class SendPaymentLinkView(APIView):
    """A human sends an offer's checkout into a conversation (same guard as the agent)."""

    def post(self, request, workspace_id, pk):
        from apps.crm.views import conversations_for

        from .payments import create_checkout

        conversation = get_object_or_404(conversations_for(request, workspace_id), pk=pk)
        offer = get_object_or_404(
            Offer.objects.for_workspace(workspace_id), pk=request.data.get("offer"), active=True
        )
        key = request.headers.get("Idempotency-Key", "")
        if not 1 <= len(key) <= 100:
            raise serializers.ValidationError("Supply an Idempotency-Key.")
        try:
            payment = create_checkout(offer, conversation, f"human:{pk}:{key}")
        except ValueError as exc:
            raise serializers.ValidationError(
                {
                    "payments_not_connected": "Connect Stripe under Integrations first.",
                    "lead_opted_out": "This lead has opted out.",
                }.get(str(exc), "Unable to create a checkout.")
            ) from None
        from apps.crm.services import queue_reply

        text = f"{offer.name}: {payment.checkout_url}"
        item = queue_reply(conversation, text, f"payment:{payment.id}", actor=request.user)
        return Response({"payment_id": payment.id, "delivery_id": item.id}, status=202)


class BillingJobView(APIView):
    def get(self, request, workspace_id, job_id):
        from django.shortcuts import get_object_or_404

        workspace_membership(request, workspace_id, ["owner"], allow_pending=True)
        job = get_object_or_404(BillingJob.objects.for_workspace(workspace_id), pk=job_id)
        return Response({"id": job.id, "status": job.status, "result": json.loads(job.result)})
