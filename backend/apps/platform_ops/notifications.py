"""Scheduled notices and per-user delivery/read/acknowledgement history."""

from urllib.parse import urlsplit

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Announcement, AnnouncementNotification


def eligible_notices(*, page="", plan=None):
    now = timezone.now()
    rows = (
        Announcement.objects.filter(is_active=True)
        .filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now),
            Q(ends_at__isnull=True) | Q(ends_at__gt=now),
        )
        .prefetch_related("target_plans")
    )
    for item in rows:
        if item.pages() and page not in item.pages():
            continue
        plans = list(item.target_plans.all())
        if plans and plan not in plans:
            continue
        yield item


def viewer_plan(request):
    workspace_id = request.query_params.get("workspace_id")
    if not workspace_id:
        return None
    from apps.billing.services import account_for
    from apps.tenants.permissions import workspace_membership

    workspace_id = serializers.UUIDField().run_validation(workspace_id)
    workspace_membership(request, workspace_id, allow_pending=True)
    price = getattr(account_for(workspace_id), "plan_price", None)
    return getattr(price, "plan", None)


def safe_link(value):
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme in {"http", "https"} and parsed.netloc else ""
    except ValueError:
        return ""


def deliver_notice(item, user):
    legacy = item.views.filter(user=user).first() if item.revision == 1 else None
    record, created = AnnouncementNotification.objects.get_or_create(
        user=user,
        announcement=item,
        revision=item.revision,
        defaults={
            "title": item.title or item.name,
            "body": item.body,
            "link_url": safe_link(item.link_url),
            "tone": item.tone,
            "requires_acknowledgement": item.requires_acknowledgement,
            "expires_at": item.ends_at,
            "read_at": legacy.created_at if legacy else None,
            "acknowledged_at": legacy.created_at if legacy else None,
        },
    )
    if created:
        # A revised notice replaces its predecessor in the unread queue, while
        # both snapshots remain available in the user's history.
        AnnouncementNotification.objects.filter(
            user=user, announcement=item, revision__lt=item.revision, read_at__isnull=True
        ).update(read_at=timezone.now())
    return record


class NotificationPage(PageNumberPagination):
    page_size = 20


class NotificationUpdate(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    all_read = serializers.BooleanField(default=False)
    acknowledge = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if attrs["all_read"]:
            if "id" in attrs or attrs["acknowledge"]:
                raise serializers.ValidationError(
                    "Mark all read cannot acknowledge a notification."
                )
        elif "id" not in attrs:
            raise serializers.ValidationError({"id": "Choose a notification."})
        return attrs


class NotificationFeedView(APIView):
    def get(self, request):
        plan = viewer_plan(request)
        for item in eligible_notices(page=request.query_params.get("section", "")[:100], plan=plan):
            deliver_notice(item, request.user)
        rows = AnnouncementNotification.objects.filter(user=request.user)
        pager = NotificationPage()
        page = pager.paginate_queryset(rows, request)
        now = timezone.now()
        response = pager.get_paginated_response(
            [
                {
                    "id": str(item.pk),
                    "title": item.title,
                    "body": item.body,
                    "link_url": item.link_url,
                    "tone": item.tone,
                    "delivered_at": item.delivered_at,
                    "read_at": item.read_at,
                    "acknowledged_at": item.acknowledged_at,
                    "requires_acknowledgement": item.requires_acknowledgement,
                    "expired": bool(item.expires_at and item.expires_at <= now),
                }
                for item in page
            ]
        )
        response.data["unread_count"] = rows.filter(read_at__isnull=True).count()
        return response

    def patch(self, request):
        serializer = NotificationUpdate(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        now = timezone.now()
        rows = AnnouncementNotification.objects.filter(user=request.user)
        if data["all_read"]:
            rows.filter(read_at__isnull=True).update(read_at=now)
        else:
            item = get_object_or_404(rows, pk=data["id"])
            item.read_at = item.read_at or now
            if data["acknowledge"]:
                item.acknowledged_at = item.acknowledged_at or now
            item.save(update_fields=["read_at", "acknowledged_at"])
        return Response(status=204)
