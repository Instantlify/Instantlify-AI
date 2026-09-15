import json

import stripe
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.models import UsageRecord
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import BillingAccount, BillingEvent, BillingJob, Offer, Payment
from .services import account_for


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
    customer = event["data"]["object"].get("customer")
    account = BillingAccount.all_objects.filter(customer_id=customer).first() if customer else None
    if account:
        with transaction.atomic():
            BillingEvent.objects.for_workspace(account.workspace_id).get_or_create(
                event_id=event["id"],
                defaults={"workspace_id": account.workspace_id, "payload": request.body.decode()},
            )
    return HttpResponse(status=200)


class BillingView(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        account = account_for(workspace_id)
        usage = UsageRecord.objects.for_workspace(workspace_id).filter(
            created_at__gte=account.period_start, kind="generation"
        )
        return Response(
            {
                "plan": account.plan,
                "status": account.status,
                "used": usage.count(),
                "usage_limit": account.usage_limit,
                "seat_limit": account.seat_limit,
                "channel_limit": account.channel_limit,
                "stripe_configured": bool(settings.STRIPE_SECRET_KEY),
                "period_start": account.period_start,
                "plans": settings.PLAN_LIMITS,
            }
        )

    def post(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner"])
        kind = request.data.get("kind", "checkout")
        plan = request.data.get("plan", "")
        key = request.headers.get("Idempotency-Key", "")
        if (
            kind not in {"checkout", "portal"}
            or (kind == "checkout" and plan not in settings.PLAN_LIMITS)
            or not 1 <= len(key) <= 100
        ):
            raise serializers.ValidationError("Supply a valid plan, action and Idempotency-Key.")
        job, _ = BillingJob.objects.for_workspace(workspace_id).get_or_create(
            request_key=key, defaults={"workspace_id": workspace_id, "kind": kind, "plan": plan}
        )
        return Response(
            {"id": job.id, "status": job.status, "result": json.loads(job.result)}, status=202
        )


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

        workspace_membership(request, workspace_id, ["owner"])
        job = get_object_or_404(BillingJob.objects.for_workspace(workspace_id), pk=job_id)
        return Response({"id": job.id, "status": job.status, "result": json.loads(job.result)})
