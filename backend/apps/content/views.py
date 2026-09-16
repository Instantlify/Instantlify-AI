import re

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.channels.models import ChannelConnection
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import BioPage, ScheduledPost


class PostSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The default manager fails closed; offer only this tenant's connections.
        self.fields["connection"].queryset = ChannelConnection.objects.for_workspace(
            self.context["workspace_id"]
        )

    class Meta:
        model = ScheduledPost
        fields = [
            "id",
            "connection",
            "caption",
            "media_url",
            "media_type",
            "scheduled_at",
            "status",
            "attempts",
            "provider_post_id",
            "error_code",
            "published_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "attempts",
            "provider_post_id",
            "error_code",
            "published_at",
            "created_at",
        ]

    def validate_media_url(self, value):
        if not value.startswith("https://"):
            raise serializers.ValidationError("Media must be served over HTTPS.")
        return value

    def validate_media_type(self, value):
        if value not in {"image", "video"}:
            raise serializers.ValidationError("Media type must be image or video.")
        return value

    def validate_scheduled_at(self, value):
        if value < timezone.now():
            raise serializers.ValidationError("Choose a time in the future.")
        return value

    def validate_connection(self, value):
        if value.workspace_id != self.context["workspace_id"] or value.status != "active":
            raise serializers.ValidationError("Choose an active connection in this workspace.")
        if value.provider not in {"instagram"}:
            raise serializers.ValidationError("Post scheduling is available for Instagram.")
        return value


class PostList(generics.ListCreateAPIView):
    serializer_class = PostSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "workspace_id": self.kwargs["workspace_id"]}

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"])
        query = ScheduledPost.objects.for_workspace(self.kwargs["workspace_id"])
        if self.request.query_params.get("upcoming"):
            query = query.filter(scheduled_at__gte=timezone.now() - timezone.timedelta(days=1))
        return query.order_by("scheduled_at")

    def perform_create(self, serializer):
        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        item = serializer.save(workspace=member.workspace)
        audit(member.workspace, self.request.user, "post.scheduled", item.id)


class PostDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PostSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "workspace_id": self.kwargs["workspace_id"]}

    def get_queryset(self):
        roles = None if self.request.method == "GET" else ["owner", "admin"]
        workspace_membership(self.request, self.kwargs["workspace_id"], roles)
        return ScheduledPost.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_update(self, serializer):
        if serializer.instance.status != "scheduled":
            raise serializers.ValidationError("Only scheduled posts can be edited.")
        item = serializer.save()
        audit(item.workspace, self.request.user, "post.updated", item.id)

    def perform_destroy(self, instance):
        if instance.status not in {"scheduled", "failed"}:
            raise serializers.ValidationError("A post that is publishing cannot be cancelled.")
        instance.status = "cancelled"
        instance.save(update_fields=["status"])
        audit(instance.workspace, self.request.user, "post.cancelled", instance.id)


RESERVED_SLUGS = {"api", "app", "admin", "p", "health", "webhooks", "media", "static", "www"}


class BioSerializer(serializers.ModelSerializer):
    class Meta:
        model = BioPage
        fields = ["id", "slug", "title", "bio", "avatar_url", "accent", "links", "published"]
        read_only_fields = ["id"]

    def validate_slug(self, value):
        value = value.lower()
        if (
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,58}[a-z0-9])?", value)
            or value in RESERVED_SLUGS
        ):
            raise serializers.ValidationError("Use 3–60 lowercase letters, digits or dashes.")
        return value

    def validate_accent(self, value):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise serializers.ValidationError("Accent must be a hex colour like #347359.")
        return value

    def validate_avatar_url(self, value):
        if value and not value.startswith("https://"):
            raise serializers.ValidationError("Avatar must be served over HTTPS.")
        return value

    def validate_links(self, value):
        if not isinstance(value, list) or len(value) > 20:
            raise serializers.ValidationError("Add up to 20 links.")
        cleaned = []
        for link in value:
            if not isinstance(link, dict):
                raise serializers.ValidationError("Each link needs a title and URL.")
            title = str(link.get("title", "")).strip()[:60]
            url = str(link.get("url", "")).strip()
            if not title or not (url.startswith("https://") or url.startswith("mailto:")):
                raise serializers.ValidationError("Links need a title and an HTTPS URL.")
            cleaned.append({"title": title, "url": url[:2000]})
        return cleaned


class BioView(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id)
        page = BioPage.objects.for_workspace(workspace_id).first()
        return Response(BioSerializer(page).data if page else {})

    def put(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        page = BioPage.objects.for_workspace(workspace_id).first()
        serializer = BioSerializer(page, data=request.data, partial=bool(page))
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                page = serializer.save(workspace=member.workspace)
        except IntegrityError:
            raise serializers.ValidationError({"slug": "That link is already taken."}) from None
        audit(member.workspace, request.user, "bio.updated", page.id)
        return Response(BioSerializer(page).data)


class PublicBioView(APIView):
    """Anonymous read of a published page. Only display fields leave the server."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def get(self, request, slug):
        page = get_object_or_404(BioPage.all_objects, slug=slug.lower(), published=True)
        from apps.tenants.branding import effective_branding

        return Response(
            {
                "slug": page.slug,
                "title": page.title,
                "bio": page.bio,
                "avatar_url": page.avatar_url,
                "accent": page.accent,
                "links": [{"index": i, **link} for i, link in enumerate(page.links)],
                "branding": effective_branding(page.workspace),
            }
        )

    def post(self, request, slug):
        """Click tracking feeds the funnel; the redirect target is validated server-side."""
        from apps.analytics.services import record

        page = get_object_or_404(BioPage.all_objects, slug=slug.lower(), published=True)
        try:
            index = int(request.data.get("index"))
            link = page.links[index]
        except (TypeError, ValueError, IndexError):
            return Response({"detail": "Unknown link."}, status=404)
        record(page.workspace_id, "link_click", provider="bio")
        return Response({"url": link["url"]})
