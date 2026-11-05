import uuid
from urllib.parse import urlsplit

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import CreatorKit


class CreatorSerializer(serializers.ModelSerializer):
    live_statistics = serializers.SerializerMethodField()

    def get_live_statistics(self, obj):
        from apps.channels.models import ChannelConnection
        from apps.platform_ops.capabilities import has_capability

        if not has_capability(obj.workspace_id, "meta_analytics"):
            return []
        rows = []
        for connection in ChannelConnection.objects.for_workspace(obj.workspace_id).filter(
            pk__in=obj.live_connection_ids,
            provider="instagram",
            status="active",
            is_test=False,
            expires_at__gt=timezone.now(),
        ):
            profile = connection.profile or {}
            value = profile.get("followers_count")
            if type(value) is int and value >= 0:
                rows.append(
                    {
                        "label": "Instagram followers",
                        "value": str(value),
                        "account": connection.display_name,
                        "as_of": profile.get("creator_stats_checked_at")
                        or connection.created_at.isoformat(),
                    }
                )
        return rows

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
            "live_connection_ids",
            "live_statistics",
            "live_stats_next_at",
            "live_stats_checked_at",
            "live_stats_error",
            "services",
            "published",
            "updated_at",
        ]
        read_only_fields = [
            "updated_at",
            "live_statistics",
            "live_stats_next_at",
            "live_stats_checked_at",
            "live_stats_error",
        ]

    def validate_live_connection_ids(self, value):
        from apps.billing.gating import check_connection_unlocked, check_feature
        from apps.channels.models import ChannelConnection

        if not isinstance(value, list) or len(value) > 10:
            raise serializers.ValidationError("Choose up to ten Instagram accounts.")
        try:
            ids = list(dict.fromkeys(str(uuid.UUID(item)) for item in value))
        except (ValueError, TypeError, AttributeError):
            raise serializers.ValidationError("Choose valid connected accounts.") from None
        workspace_id = self.context["workspace_id"]
        if ids:
            from apps.platform_ops.capabilities import check_capability

            check_capability(workspace_id, "meta_analytics")
            check_feature(workspace_id, "integrations_unlocked")
        connections = list(
            ChannelConnection.objects.for_workspace(workspace_id).filter(
                pk__in=ids,
                provider="instagram",
                status="active",
                is_test=False,
                expires_at__gt=timezone.now(),
            )
        )
        if len(connections) != len(ids):
            raise serializers.ValidationError("Choose active connected Instagram accounts.")
        for connection in connections:
            check_connection_unlocked(connection)
        return ids

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
            old_ids = item.live_connection_ids if item else []
            serializer = CreatorSerializer(
                item, data=request.data, context={"workspace_id": workspace_id}
            )
            serializer.is_valid(raise_exception=True)
            try:
                with transaction.atomic():
                    item = serializer.save(workspace=member.workspace)
                    if item.live_connection_ids != old_ids:
                        item.live_stats_next_at = (
                            timezone.now() if item.live_connection_ids else None
                        )
                        item.live_stats_token, item.live_stats_started_at, item.live_stats_error = (
                            None,
                            None,
                            "",
                        )
                        item.save()
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
        data = dict(CreatorSerializer(item).data)
        for key in [
            "live_connection_ids",
            "live_stats_next_at",
            "live_stats_checked_at",
            "live_stats_error",
        ]:
            data.pop(key, None)
        return Response(data)
