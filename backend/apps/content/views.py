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
        from apps.billing.gating import check_connection_unlocked, check_feature
        from apps.platform_ops.capabilities import check_capability

        check_capability(member.workspace_id, "meta_publishing")
        check_feature(member.workspace_id, "content_scheduling_enabled")
        check_connection_unlocked(serializer.validated_data["connection"])
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
        from apps.platform_ops.capabilities import check_capability

        check_capability(serializer.instance.workspace_id, "meta_publishing")
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
        fields = [
            "id",
            "slug",
            "title",
            "bio",
            "avatar_url",
            "accent",
            "links",
            "blocks",
            "theme",
            "published",
        ]
        read_only_fields = ["id"]

    def validate_blocks(self, value):
        from .bio_blocks import validate_blocks

        return validate_blocks(value)

    def validate_theme(self, value):
        from .bio_blocks import THEMES

        if value not in THEMES:
            raise serializers.ValidationError("Choose a theme.")
        return value

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

        from .bio_blocks import public_block

        return Response(
            {
                "slug": page.slug,
                "title": page.title,
                "bio": page.bio,
                "avatar_url": page.avatar_url,
                "accent": page.accent,
                "theme": page.theme,
                "links": [{"index": i, **link} for i, link in enumerate(page.links)],
                "blocks": [public_block(i, block) for i, block in enumerate(page.blocks)],
                "branding": effective_branding(page.workspace),
            }
        )

    def post(self, request, slug):
        """Click tracking feeds the funnel; the redirect target is validated server-side."""
        from apps.analytics.services import record

        page = get_object_or_404(BioPage.all_objects, slug=slug.lower(), published=True)
        if "email" in request.data:
            return self.subscribe(request, page)
        try:
            if "block" in request.data:
                block = page.blocks[int(request.data.get("block"))]
                url = block.get("url") if block["type"] == "link" else block.get("link")
                if block["type"] == "social":
                    url = block["items"][int(request.data.get("item", 0))]["url"]
                if not url:
                    raise IndexError
            else:
                url = page.links[int(request.data.get("index"))]["url"]
        except (TypeError, ValueError, IndexError, KeyError):
            return Response({"detail": "Unknown link."}, status=404)
        record(page.workspace_id, "link_click", provider="bio")
        return Response({"url": url})

    def subscribe(self, request, page):
        """An email-signup block: create or tag the contact, never message them."""
        from django.core.validators import validate_email

        from apps.billing.gating import PlanLimitExceeded, check_within_limit
        from apps.crm.models import Lead
        from apps.tenants.models import Workspace

        try:
            block = page.blocks[int(request.data.get("block"))]
            if block["type"] != "email_capture":
                raise IndexError
        except (TypeError, ValueError, IndexError, KeyError):
            return Response({"detail": "Unknown signup form."}, status=404)
        email = str(request.data.get("email") or "").strip().lower()[:254]
        name = str(request.data.get("name") or "").strip()[:150]
        try:
            validate_email(email)
        except Exception:
            return Response({"detail": "Enter a valid email address."}, status=400)
        with transaction.atomic():
            Workspace.objects.select_for_update().get(pk=page.workspace_id)
            lead = Lead.objects.for_workspace(page.workspace_id).filter(email=email).first()
            if lead is None:
                try:
                    check_within_limit(page.workspace_id, "max_contacts")
                except PlanLimitExceeded:
                    return Response(
                        {"detail": "Signups are paused right now. Please try again later."},
                        status=503,
                    )
                lead = Lead.objects.for_workspace(page.workspace_id).create(
                    workspace_id=page.workspace_id,
                    name=name,
                    email=email,
                    tags=[block["tag"]],
                    fields={"source": "bio"},
                )
            elif block["tag"] not in lead.tags and len(lead.tags) < 50:
                lead.tags = [*lead.tags, block["tag"]]
                lead.save(update_fields=["tags"])
        return Response({"subscribed": True}, status=201)
