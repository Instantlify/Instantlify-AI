from urllib.parse import urlsplit

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import CreatorKit


class CreatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreatorKit
        fields = [
            "slug",
            "name",
            "headline",
            "bio",
            "contact_email",
            "links",
            "statistics",
            "services",
            "published",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_slug(self, value):
        value = value.lower()
        query = CreatorKit.all_objects.filter(slug=value)
        if self.instance:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise serializers.ValidationError("That creator address is already in use.")
        return value

    def pairs(self, value, fields, limit=12):
        if not isinstance(value, list) or len(value) > limit:
            raise serializers.ValidationError(f"Use up to {limit} entries.")
        for row in value:
            if (
                not isinstance(row, dict)
                or set(row) != set(fields)
                or any(
                    not isinstance(row.get(key), str)
                    or not 1 <= len(row[key].strip()) <= (2000 if key == "url" else 250)
                    for key in fields
                )
            ):
                raise serializers.ValidationError("Every entry needs its labelled text fields.")
        return value

    def validate_links(self, value):
        value = self.pairs(value, ["label", "url"])
        for row in value:
            try:
                url = urlsplit(row["url"])
                valid = (
                    url.scheme == "https" and url.hostname and not url.username and not url.password
                )
            except ValueError:
                valid = False
            if not valid:
                raise serializers.ValidationError("Use complete HTTPS links without credentials.")
        return value

    def validate_statistics(self, value):
        return self.pairs(value, ["label", "value"])

    def validate_services(self, value):
        return self.pairs(value, ["title", "description"])


class CreatorView(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id)
        item = CreatorKit.objects.for_workspace(workspace_id).first()
        return Response(CreatorSerializer(item).data if item else None)

    def put(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        with transaction.atomic():
            from apps.tenants.models import Workspace

            Workspace.objects.select_for_update().get(pk=workspace_id)
            item = CreatorKit.objects.for_workspace(workspace_id).first()
            serializer = CreatorSerializer(item, data=request.data)
            serializer.is_valid(raise_exception=True)
            try:
                with transaction.atomic():
                    item = serializer.save(workspace=member.workspace)
            except IntegrityError:
                raise serializers.ValidationError(
                    "That creator address is already in use."
                ) from None
            audit(member.workspace, request.user, "creator.updated", item.pk)
        return Response(CreatorSerializer(item).data)


class PublicCreatorView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        item = get_object_or_404(CreatorKit.all_objects, slug=slug, published=True)
        return Response(CreatorSerializer(item).data)
