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
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import Template, TemplateInstall

CATEGORIES = {"sales", "support", "booking", "ecommerce", "creator", "agency", "other"}


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
    @transaction.atomic
    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        template = get_object_or_404(
            published().select_for_update(), slug=str(request.data.get("slug", ""))[:140]
        )
        if template.price_cents:
            # Paid templates need a payout rail (Stripe Connect) that does not exist yet.
            raise serializers.ValidationError(
                "Paid templates cannot be installed yet. Contact the author."
            )
        automation = import_automation(
            member.workspace,
            {"format": FORMAT, "version": VERSION, "name": template.title, "graph": template.graph},
            request.user,
            installed_from=template.pk,
        )
        TemplateInstall.objects.for_workspace(workspace_id).create(
            workspace=member.workspace, template_id=template.pk, automation=automation
        )
        Template.all_objects.filter(pk=template.pk).update(install_count=F("install_count") + 1)
        return Response({"automation_id": automation.id}, status=201)
