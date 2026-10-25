"""Drafted campaigns with frozen audiences and durable, guarded deliveries."""

import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.channels.media import validate_media
from apps.channels.models import ChannelConnection
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import Campaign, CampaignRecipient, Conversation, Lead, Message

CHANNELS = {"instagram", "messenger", "whatsapp", "telegram"}


def audience_settings(value):
    if not isinstance(value, dict) or set(value) - {"mode", "lead_ids", "tags", "stages", "search"}:
        raise serializers.ValidationError("Invalid campaign audience.")
    mode = value.get("mode", "all")
    if mode not in {"all", "selected", "filtered"}:
        raise serializers.ValidationError("Choose all, filtered or selected contacts.")
    result = {"mode": mode}
    for field, limit in [("lead_ids", 10000), ("tags", 20), ("stages", 6)]:
        values = value.get(field, [])
        if (
            not isinstance(values, list)
            or len(values) > limit
            or any(not isinstance(item, str) or not 1 <= len(item) <= 100 for item in values)
        ):
            raise serializers.ValidationError("Use a bounded list of contact IDs, tags and stages.")
        if field == "lead_ids":
            try:
                values = [str(uuid.UUID(item)) for item in values]
            except ValueError:
                raise serializers.ValidationError("Invalid selected contact ID.") from None
        result[field] = list(dict.fromkeys(values))
    if mode == "selected" and not result["lead_ids"]:
        raise serializers.ValidationError(
            "Choose at least one contact; an empty selection never means everyone."
        )
    search = value.get("search", "")
    if not isinstance(search, str) or len(search) > 150:
        raise serializers.ValidationError("Search must be up to 150 characters.")
    result["search"] = search.strip()
    return result


def eligible_conversations(workspace_id, connection_id, audience):
    query = (
        Conversation.objects.for_workspace(workspace_id)
        .filter(
            identity__connection_id=connection_id,
            identity__lead__opted_out=False,
            last_inbound_at__gte=timezone.now() - timedelta(hours=24),
        )
        .select_related("identity__lead", "identity__connection")
    )
    inbound = Message.objects.for_workspace(workspace_id).filter(
        conversation_id=OuterRef("pk"), direction="inbound"
    )
    private = inbound.exclude(kind__in=["comment", "live_comment"]).filter(
        created_at__gte=timezone.now() - timedelta(hours=24)
    )
    query = query.annotate(has_inbound=Exists(inbound), private_recent=Exists(private)).filter(
        Q(private_recent=True) | Q(has_inbound=False)
    )
    mode = audience.get("mode", "all")
    if mode == "selected":
        query = query.filter(identity__lead_id__in=audience.get("lead_ids", []))
    elif mode == "filtered":
        if audience.get("stages"):
            query = query.filter(identity__lead__stage__in=audience["stages"])
        if audience.get("search"):
            text = audience["search"]
            query = query.filter(
                Q(identity__lead__name__icontains=text)
                | Q(identity__lead__email__icontains=text)
                | Q(identity__lead__handle__icontains=text)
            )
    rows = list(query.order_by("id")[:10001])
    if len(rows) > 10000:
        raise serializers.ValidationError(
            "Narrow this campaign to at most 10,000 eligible conversations."
        )
    tags = audience.get("tags", []) if mode == "filtered" else []
    return [row for row in rows if all(tag in row.identity.lead.tags for tag in tags)]


class CampaignSerializer(serializers.ModelSerializer):
    connection_id = serializers.UUIDField(required=False, allow_null=True)
    text = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    counts = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            "id",
            "name",
            "connection_id",
            "text",
            "buttons",
            "media_url",
            "media_type",
            "tag",
            "audience",
            "status",
            "scheduled_at",
            "launched_at",
            "finished_at",
            "expected_count",
            "counts",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "launched_at",
            "finished_at",
            "expected_count",
            "counts",
            "created_at",
        ]

    def get_counts(self, obj):
        return dict(
            obj.recipients.for_workspace(obj.workspace_id)
            .values_list("status")
            .annotate(total=Count("id"))
        )

    def validate_connection_id(self, value):
        if (
            value is not None
            and not ChannelConnection.objects.for_workspace(
                self.context["view"].kwargs["workspace_id"]
            )
            .filter(pk=value, provider__in=CHANNELS, status="active")
            .exists()
        ):
            raise serializers.ValidationError(
                "Choose an active messaging account in this workspace."
            )
        return value

    def validate_audience(self, value):
        return audience_settings(value)

    def validate_buttons(self, value):
        from apps.automations.services import validate_graph

        if (
            not isinstance(value, list)
            or len(value) > 3
            or any(not isinstance(item, dict) or item.get("type") != "web_url" for item in value)
        ):
            raise serializers.ValidationError("Use up to three HTTPS link buttons.")
        if value:
            validate_graph(
                {
                    "start": "message",
                    "triggers": [{"kind": "dm", "channel": "instagram", "keyword": "*"}],
                    "nodes": [
                        {
                            "id": "message",
                            "data": {"kind": "send_buttons", "text": "Campaign", "buttons": value},
                        },
                        {"id": "end", "data": {"kind": "end"}},
                    ],
                    "edges": [{"source": "message", "target": "end"}],
                }
            )
        return value

    def validate_media_type(self, value):
        if value not in {"image", "video"}:
            raise serializers.ValidationError("Choose photo or video.")
        return value

    def validate(self, attrs):
        url = attrs.get("media_url", self.instance.media_url if self.instance else "")
        if url:
            validate_media(
                url, attrs.get("media_type", self.instance.media_type if self.instance else "image")
            )
        if attrs.get("scheduled_at") and attrs["scheduled_at"] > timezone.now() + timedelta(
            days=30
        ):
            raise serializers.ValidationError("Schedule within the next 30 days.")
        return attrs


class CampaignList(generics.ListCreateAPIView):
    serializer_class = CampaignSerializer
    pagination_class = None

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return Campaign.objects.for_workspace(self.kwargs["workspace_id"])[:100]

    def perform_create(self, serializer):
        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        item = serializer.save(workspace=member.workspace)
        audit(member.workspace, self.request.user, "campaign.created", item.pk)


class CampaignDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CampaignSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return Campaign.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_update(self, serializer):
        with transaction.atomic():
            item = (
                Campaign.objects.for_workspace(self.kwargs["workspace_id"])
                .select_for_update()
                .get(pk=serializer.instance.pk)
            )
            if item.status != "draft":
                raise serializers.ValidationError("Only draft campaigns can be edited.")
            serializer.instance = item
            serializer.save()

    def perform_destroy(self, instance):
        with transaction.atomic():
            item = (
                Campaign.objects.for_workspace(instance.workspace_id)
                .select_for_update()
                .get(pk=instance.pk)
            )
            if item.status != "draft":
                raise serializers.ValidationError(
                    "Only unsent drafts can be deleted. Cancel a queued campaign instead."
                )
            item.delete()


class CampaignAudienceView(APIView):
    def post(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        serializer = CampaignSerializer(data=request.data, context={"view": self})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data.get("connection_id"):
            raise serializers.ValidationError("Choose a sending account first.")
        rows = eligible_conversations(
            workspace_id, data["connection_id"], data.get("audience", {"mode": "all"})
        )
        return Response(
            {
                "eligible": len(rows),
                "sample": [
                    {
                        "name": row.identity.lead.name or row.identity.lead.handle or "Contact",
                        "lead_id": row.identity.lead_id,
                    }
                    for row in rows[:10]
                ],
            }
        )


class LaunchCampaignView(APIView):
    def post(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        with transaction.atomic():
            item = get_object_or_404(
                Campaign.objects.for_workspace(workspace_id).select_for_update(), pk=pk
            )
            if item.status != "draft":
                return Response(CampaignSerializer(item).data)
            connection = item.connection
            if (
                not connection
                or connection.status != "active"
                or connection.expires_at <= timezone.now()
            ):
                raise serializers.ValidationError("Reconnect the sending account first.")
            from apps.billing.gating import check_connection_unlocked

            check_connection_unlocked(connection)
            if (
                not item.text.strip()
                and not item.media_url
                or item.buttons
                and not item.text.strip()
            ):
                raise serializers.ValidationError(
                    "Write a message or add media. Link buttons need message text."
                )
            audience = audience_settings(item.audience)
            rows = eligible_conversations(workspace_id, connection.pk, audience)
            if not rows:
                raise serializers.ValidationError(
                    "No contacts currently match with an open messaging window."
                )
            CampaignRecipient.objects.for_workspace(workspace_id).bulk_create(
                [
                    CampaignRecipient(
                        workspace_id=workspace_id,
                        campaign=item,
                        conversation=row,
                        lead=row.identity.lead,
                    )
                    for row in rows
                ]
            )
            item.expected_count = len(rows)
            item.status = "queued"
            item.launched_at = timezone.now()
            item.save()
            audit(member.workspace, request.user, "campaign.launched", item.pk)
        return Response(CampaignSerializer(item).data, status=202)


class CancelCampaignView(APIView):
    def post(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        with transaction.atomic():
            item = get_object_or_404(
                Campaign.objects.for_workspace(workspace_id).select_for_update(), pk=pk
            )
            if item.status in {"queued", "sending"}:
                item.recipients.for_workspace(workspace_id).filter(status="pending").update(
                    status="cancelled", error_code="campaign_cancelled"
                )
                item.status, item.finished_at = "cancelled", timezone.now()
                item.save()
                audit(member.workspace, request.user, "campaign.cancelled", item.pk)
        return Response(CampaignSerializer(item).data)


class CampaignRecipientsView(APIView):
    def get(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        campaign = get_object_or_404(Campaign.objects.for_workspace(workspace_id), pk=pk)
        return Response(
            [
                {
                    "id": row.pk,
                    "lead_id": row.lead_id,
                    "name": (row.lead.name or row.lead.handle or "Contact")
                    if row.lead
                    else "Deleted contact",
                    "status": row.status,
                    "error_code": row.error_code,
                }
                for row in campaign.recipients.for_workspace(workspace_id)
                .select_related("lead")
                .order_by("created_at", "id")[:1000]
            ]
        )


def process_campaign(workspace_id, campaign_id):
    from .services import queue_reply

    with transaction.atomic():
        campaign = (
            Campaign.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=campaign_id, status__in=["queued", "sending", "cancelled"])
            .first()
        )
        if not campaign or campaign.scheduled_at and campaign.scheduled_at > timezone.now():
            return
        if campaign.status != "cancelled":
            campaign.status = "sending"
        for row in (
            campaign.recipients.for_workspace(workspace_id)
            .filter(status="queued")
            .select_related("text_delivery", "media_delivery", "lead")[:100]
        ):
            deliveries = [item for item in [row.text_delivery, row.media_delivery] if item]
            statuses = {item.status for item in deliveries}
            if "unknown" in statuses:
                row.status, row.error_code = "unknown", "delivery_result_unknown"
            elif "failed" in statuses or not deliveries:
                row.status, row.error_code = "failed", "delivery_failed_or_removed"
            elif statuses == {"sent"}:
                row.status = "sent"
                if campaign.tag and row.lead_id:
                    lead = (
                        Lead.objects.for_workspace(workspace_id)
                        .select_for_update()
                        .filter(pk=row.lead_id)
                        .first()
                    )
                    if lead and campaign.tag not in lead.tags:
                        lead.tags = [*lead.tags, campaign.tag]
                        lead.save(update_fields=["tags"])
            row.save()
        if campaign.status != "cancelled":
            for row in (
                campaign.recipients.for_workspace(workspace_id)
                .filter(status="pending")
                .select_related(
                    "conversation__identity__lead", "conversation__identity__connection"
                )[:25]
            ):
                try:
                    with transaction.atomic():
                        if (
                            not row.conversation
                            or row.conversation.identity.connection_id != campaign.connection_id
                        ):
                            raise serializers.ValidationError(
                                "The contact or account is unavailable."
                            )
                        text = campaign.text.replace(
                            "{{name}}", row.conversation.identity.lead.name[:150]
                        )
                        key = f"broadcast:campaign:{campaign.pk}:{row.pk}"
                        if text:
                            row.text_delivery = queue_reply(
                                row.conversation,
                                text,
                                key + ":text",
                                buttons=campaign.buttons or None,
                            )
                        if campaign.media_url:
                            row.media_delivery = queue_reply(
                                row.conversation,
                                "",
                                key + ":media",
                                media_url=campaign.media_url,
                                media_type=campaign.media_type,
                            )
                        row.status = "queued"
                        row.save()
                except serializers.ValidationError:
                    row.status, row.error_code = "skipped", "window_opt_out_or_account_guard"
                    row.save()
            if (
                not campaign.recipients.for_workspace(workspace_id)
                .filter(status__in=["pending", "queued"])
                .exists()
            ):
                campaign.status, campaign.finished_at = "completed", timezone.now()
        campaign.save()
