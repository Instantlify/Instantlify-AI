import secrets

from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.automations.models import Automation
from apps.automations.templates import FORMAT, VERSION, import_automation
from apps.channels.transport import ProviderError
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from . import services
from .models import SellerAccount, Template, TemplateInstall, TemplatePurchase

CATEGORIES = {"sales", "support", "booking", "ecommerce", "creator", "agency", "other"}

PURCHASE_ERRORS = {
    "stripe_not_configured": "Marketplace payments are not configured on this server.",
    "seller_unavailable": "The author cannot receive payouts right now. Try again later.",
    "purchase_not_paid": "This purchase has not been paid.",
    "template_missing": "The template no longer exists.",
    "template_invalid": "The template failed validation. Contact the author.",
    "payment_provider_error": "The payment provider rejected the request. Try again.",
    "platform_paused": "Marketplace purchases are paused right now.",
}


def purchase_error(exc):
    return serializers.ValidationError(
        PURCHASE_ERRORS.get(getattr(exc, "code", str(exc)), "Unable to complete the purchase.")
    )


class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "category",
            "author_name",
            "price_cents",
            "status",
            "install_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class TemplateDetailSerializer(TemplateSerializer):
    class Meta(TemplateSerializer.Meta):
        fields = TemplateSerializer.Meta.fields + ["graph"]
        read_only_fields = fields


class PurchaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplatePurchase
        fields = [
            "id",
            "template_id",
            "title",
            "amount_cents",
            "currency",
            "status",
            "automation_id",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields


def seller_payload(seller):
    if not seller:
        return {"connected": False, "transfers_status": "none", "requirements_due": False}
    return {
        "connected": True,
        "transfers_status": seller.transfers_status,
        "requirements_due": seller.requirements_due,
        "can_sell": services.can_receive(seller),
        "checked_at": seller.checked_at,
        "country": seller.country,
    }


def published():
    return Template.all_objects.filter(status="published")


class PublicTemplateList(generics.ListAPIView):
    """Community listing. Anonymous read; templates are cross-tenant by design."""

    permission_classes = [AllowAny]
    serializer_class = TemplateSerializer

    def get_queryset(self):
        query = published()
        search = self.request.query_params.get("search", "")[:100]
        category = self.request.query_params.get("category", "")
        if search:
            query = query.filter(Q(title__icontains=search) | Q(description__icontains=search))
        if category in CATEGORIES:
            query = query.filter(category=category)
        return query


class PublicTemplateDetail(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = TemplateDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return published()


class PublishTemplateView(APIView):
    """Publish one of this workspace's automations to the marketplace."""

    @transaction.atomic
    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        automation = get_object_or_404(
            Automation.objects.for_workspace(workspace_id), pk=request.data.get("automation")
        )
        if not automation.published:
            raise serializers.ValidationError("Publish the automation before sharing it.")
        title = str(request.data.get("title", automation.name)).strip()[:120]
        description = str(request.data.get("description", ""))[:2000]
        category = request.data.get("category", "sales")
        if not title:
            raise serializers.ValidationError("Give the template a title.")
        if category not in CATEGORIES:
            raise serializers.ValidationError("Unsupported category.")
        try:
            price = int(request.data.get("price_cents", 0))
        except (TypeError, ValueError):
            raise serializers.ValidationError("Price must be a whole number of cents.") from None
        if price < 0 or price > 100000:
            raise serializers.ValidationError("Price must be between 0 and $1000.")
        if 0 < price < 100:
            raise serializers.ValidationError("Paid templates must cost at least $1.")
        if price:
            seller = SellerAccount.objects.for_workspace(workspace_id).first()
            if not services.can_receive(seller):
                raise serializers.ValidationError(
                    "Connect payouts (Stripe) before publishing a paid template."
                )
        template = (
            Template.objects.for_workspace(workspace_id)
            .filter(source_automation_id=automation.pk)
            .first()
        )
        graph = {key: automation.published[key] for key in ["start", "nodes", "edges", "triggers"]}
        fields = {
            "title": title,
            "description": description,
            "category": category,
            "graph": graph,
            "author_name": member.workspace.name,
            "price_cents": price,
            "status": "published",
        }
        if template:
            for key, value in fields.items():
                setattr(template, key, value)
            template.save()
        else:
            template = Template.objects.for_workspace(workspace_id).create(
                workspace=member.workspace,
                slug=f"{slugify(title)[:100] or 'template'}-{secrets.token_hex(3)}",
                source_automation_id=automation.pk,
                **fields,
            )
        audit(member.workspace, request.user, "template.published", template.id)
        return Response(TemplateSerializer(template).data, status=201)


class MyTemplateList(generics.ListAPIView):
    serializer_class = TemplateSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return Template.objects.for_workspace(self.kwargs["workspace_id"]).order_by("-created_at")


class MyTemplateDetail(APIView):
    def delete(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        template = get_object_or_404(Template.objects.for_workspace(workspace_id), pk=pk)
        template.status = "unlisted"
        template.save(update_fields=["status"])
        audit(member.workspace, request.user, "template.unlisted", template.id)
        return Response(status=204)


class InstallTemplateView(APIView):
    """Free templates (and the author's own) install immediately (201). Paid templates
    return 202 with a Stripe Checkout URL; the install happens once payment is confirmed."""

    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        with transaction.atomic():
            template = get_object_or_404(
                published().select_for_update(), slug=str(request.data.get("slug", ""))[:140]
            )
            if not template.price_cents or template.workspace_id == member.workspace_id:
                automation = import_automation(
                    member.workspace,
                    {
                        "format": FORMAT,
                        "version": VERSION,
                        "name": template.title,
                        "graph": template.graph,
                    },
                    request.user,
                    installed_from=template.pk,
                )
                TemplateInstall.objects.for_workspace(workspace_id).create(
                    workspace=member.workspace, template_id=template.pk, automation=automation
                )
                Template.all_objects.filter(pk=template.pk).update(
                    install_count=F("install_count") + 1
                )
                return Response({"automation_id": automation.id}, status=201)
        key = str(request.data.get("idempotency_key") or request.headers.get("Idempotency-Key", ""))
        if not 1 <= len(key) <= 100:
            raise serializers.ValidationError("Supply an idempotency_key for a paid install.")
        try:
            purchase = services.start_purchase(
                member.workspace, request.user, template, f"install:{template.pk}:{key}"
            )
            if purchase.status == "paid":
                services.install_purchase(purchase, request.user)
        except (ValueError, ProviderError) as exc:
            raise purchase_error(exc) from None
        if purchase.status == "installed":
            return Response({"automation_id": purchase.automation_id}, status=201)
        return Response(
            {
                "purchase_id": purchase.id,
                "status": purchase.status,
                "checkout_url": purchase.checkout_url,
            },
            status=202,
        )


class PurchaseList(generics.ListAPIView):
    serializer_class = PurchaseSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return TemplatePurchase.objects.for_workspace(self.kwargs["workspace_id"])


class PurchaseDetail(APIView):
    """GET the state; POST re-checks Stripe (webhook fallback) and installs if paid."""

    def get(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        purchase = get_object_or_404(TemplatePurchase.objects.for_workspace(workspace_id), pk=pk)
        return Response(PurchaseSerializer(purchase).data)

    def post(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        purchase = get_object_or_404(TemplatePurchase.objects.for_workspace(workspace_id), pk=pk)
        try:
            purchase = services.sync_purchase(purchase)
            if purchase.status == "paid":
                services.install_purchase(purchase, request.user)
        except (ValueError, ProviderError) as exc:
            raise purchase_error(exc) from None
        return Response(PurchaseSerializer(purchase).data)


class PayoutView(APIView):
    """Author-side Stripe Connect onboarding (owner only for anything that hits Stripe)."""

    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        seller = SellerAccount.objects.for_workspace(workspace_id).first()
        return Response(seller_payload(seller))

    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner"])
        action = request.data.get("action", "onboard")
        country = str(request.data.get("country", "us")).lower()
        if action not in {"onboard", "refresh", "dashboard"}:
            raise serializers.ValidationError("Unknown action.")
        if len(country) != 2 or not country.isalpha():
            raise serializers.ValidationError("Country must be an ISO 3166-1 alpha-2 code.")
        seller = SellerAccount.objects.for_workspace(workspace_id).first()
        try:
            if action == "onboard":
                seller = seller or services.ensure_seller(member.workspace, request.user, country)
                url = services.onboarding_link(seller)
                audit(member.workspace, request.user, "marketplace.onboarding_started", seller.id)
                return Response({**seller_payload(seller), "url": url}, status=202)
            if not seller:
                raise serializers.ValidationError("Set up payouts first.")
            if action == "refresh":
                seller = services.sync_seller(seller)
                return Response(seller_payload(seller))
            return Response({**seller_payload(seller), "url": services.dashboard_link(seller)})
        except (ValueError, ProviderError) as exc:
            raise purchase_error(exc) from None
