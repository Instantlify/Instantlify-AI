import json
import secrets

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Membership, Workspace
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import (
    ChannelIdentity,
    Conversation,
    IntegrationConfig,
    IntegrationJob,
    InternalNote,
    Lead,
    Message,
)
from .services import notify, queue_reply


def conversations_for(request, workspace_id):
    member = workspace_membership(request, workspace_id)
    query = Conversation.objects.for_workspace(workspace_id)
    if member.role == "agent":
        query = query.filter(Q(assigned_to=request.user) | Q(assigned_to__isnull=True))
    return query.select_related("identity__lead", "identity__connection")


class ConversationSerializer(serializers.ModelSerializer):
    lead = serializers.SerializerMethodField()
    provider = serializers.CharField(source="identity.connection.provider", read_only=True)
    is_test = serializers.BooleanField(source="identity.connection.is_test", read_only=True)

    def get_lead(self, obj):
        lead = obj.identity.lead
        return {
            "id": lead.id,
            "name": lead.name,
            "email": lead.email,
            "stage": lead.stage,
            "tags": lead.tags,
            "fields": lead.fields,
            "opted_out": lead.opted_out,
        }

    class Meta:
        model = Conversation
        fields = [
            "id",
            "lead",
            "provider",
            "is_test",
            "assigned_to",
            "status",
            "ai_enabled",
            "last_inbound_at",
            "updated_at",
        ]


class ConversationList(generics.ListAPIView):
    serializer_class = ConversationSerializer

    def get_queryset(self):
        query = conversations_for(self.request, self.kwargs["workspace_id"])
        search = self.request.query_params.get("search", "")[:100]
        if search:
            query = query.filter(
                Q(identity__lead__name__icontains=search)
                | Q(identity__lead__email__icontains=search)
            )
        return query


class ConversationDetail(APIView):
    @transaction.atomic
    def patch(self, request, workspace_id, pk):
        conversation = get_object_or_404(
            conversations_for(request, workspace_id).select_for_update(), pk=pk
        )
        member = workspace_membership(request, workspace_id)
        if "assigned_to" in request.data:
            user_id = request.data["assigned_to"]
            if member.role == "agent" and user_id != request.user.id:
                raise serializers.ValidationError(
                    "Agents may only claim conversations for themselves."
                )
            if (
                user_id is not None
                and not Membership.objects.for_workspace(workspace_id)
                .filter(user_id=user_id)
                .exists()
            ):
                raise serializers.ValidationError("Assignee must be a workspace member.")
            conversation.assigned_to_id = user_id
        if "status" in request.data:
            if request.data["status"] not in {"open", "closed", "needs_human"}:
                raise serializers.ValidationError("Invalid conversation status.")
            conversation.status = request.data["status"]
        if "ai_enabled" in request.data:
            if not isinstance(request.data["ai_enabled"], bool):
                raise serializers.ValidationError("ai_enabled must be boolean.")
            conversation.ai_enabled = request.data["ai_enabled"]
        conversation.save()
        audit(conversation.workspace, request.user, "conversation.updated", conversation.id)
        transaction.on_commit(lambda: notify(workspace_id))
        return Response(ConversationSerializer(conversation).data)


class MessageSerializer(serializers.ModelSerializer):
    delivery_status = serializers.CharField(source="delivery.status", default=None, read_only=True)

    class Meta:
        model = Message
        fields = ["id", "direction", "text", "kind", "created_at", "delivery_status"]


class MessageList(generics.ListAPIView):
    serializer_class = MessageSerializer

    def get_queryset(self):
        conversation = get_object_or_404(
            conversations_for(self.request, self.kwargs["workspace_id"]), pk=self.kwargs["pk"]
        )
        return (
            Message.objects.for_workspace(conversation.workspace_id)
            .filter(conversation=conversation)
            .select_related("delivery")
            .order_by("-created_at", "-id")
        )

    def post(self, request, workspace_id, pk):
        conversation = get_object_or_404(conversations_for(request, workspace_id), pk=pk)
        text = request.data.get("text")
        key = request.headers.get("Idempotency-Key", "")
        if not isinstance(text, str) or not 1 <= len(text) <= 2000 or not 1 <= len(key) <= 100:
            raise serializers.ValidationError(
                "Supply text (1–2000 characters) and an Idempotency-Key."
            )
        item = queue_reply(conversation, text, f"human:{pk}:{key}", actor=request.user)
        return Response({"id": item.id, "status": item.status}, status=202)


class NotesView(APIView):
    def get(self, request, workspace_id, pk):
        conversation = get_object_or_404(conversations_for(request, workspace_id), pk=pk)
        return Response(
            list(
                InternalNote.objects.for_workspace(workspace_id)
                .filter(conversation=conversation)
                .values("id", "text", "author_id", "created_at")[:100]
            )
        )

    def post(self, request, workspace_id, pk):
        conversation = get_object_or_404(conversations_for(request, workspace_id), pk=pk)
        text = request.data.get("text", "")
        if not isinstance(text, str) or not 1 <= len(text) <= 5000:
            raise serializers.ValidationError("A note must have 1–5000 characters.")
        note = InternalNote.objects.for_workspace(workspace_id).create(
            workspace_id=workspace_id, conversation=conversation, author=request.user, text=text
        )
        audit(conversation.workspace, request.user, "note.created", note.id)
        return Response({"id": note.id}, status=201)


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = ["id", "name", "email", "stage", "tags", "fields", "opted_out"]
        read_only_fields = ["id"]

    def validate_stage(self, value):
        if value not in {"new", "qualified", "interested", "booked", "won", "lost"}:
            raise serializers.ValidationError("Invalid stage.")
        return value


class LeadList(generics.ListAPIView):
    serializer_class = LeadSerializer

    def get_queryset(self):
        member = workspace_membership(self.request, self.kwargs["workspace_id"])
        query = Lead.objects.for_workspace(member.workspace_id)
        if member.role == "agent":
            ids = conversations_for(self.request, member.workspace_id).values_list(
                "identity__lead_id", flat=True
            )
            query = query.filter(pk__in=ids)
        return query


class LeadDetail(generics.RetrieveUpdateAPIView):
    serializer_class = LeadSerializer

    def get_queryset(self):
        ids = conversations_for(self.request, self.kwargs["workspace_id"]).values_list(
            "identity__lead_id", flat=True
        )
        return Lead.objects.for_workspace(self.kwargs["workspace_id"]).filter(pk__in=ids)

    def perform_update(self, serializer):
        from apps.public_api.services import emit, lead_payload

        lead = serializer.save()
        audit(lead.workspace, self.request.user, "lead.updated", lead.id)
        emit(lead.workspace_id, "lead.updated", lead_payload(lead))


class MergeLeadView(APIView):
    @transaction.atomic
    def post(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        target = get_object_or_404(Lead.objects.for_workspace(workspace_id), pk=pk)
        source = get_object_or_404(
            Lead.objects.for_workspace(workspace_id), pk=request.data.get("source_id")
        )
        if source.pk == target.pk:
            raise serializers.ValidationError("Choose two different leads.")
        Workspace.objects.select_for_update().get(pk=workspace_id)
        ChannelIdentity.objects.for_workspace(workspace_id).filter(lead=source).update(lead=target)
        target.tags = sorted(set(target.tags + source.tags))
        target.opted_out = target.opted_out or source.opted_out
        target.fields = {**source.fields, **target.fields}
        target.save(update_fields=["tags", "opted_out", "fields"])
        source.delete()
        audit(member.workspace, request.user, "leads.merged", target.id)
        return Response(LeadSerializer(target).data)


class IntegrationSerializer(serializers.ModelSerializer):
    credentials = serializers.JSONField(write_only=True)
    configured = serializers.SerializerMethodField()

    def get_configured(self, obj):
        return bool(json.loads(obj.credentials))

    def validate_provider(self, value):
        if value not in {
            "google_calendar",
            "calcom",
            "airtable",
            "notion",
            "gohighlevel",
            "attio",
            "slack",
            "elevenlabs",
            "stripe",
        }:
            raise serializers.ValidationError("Unsupported provider.")
        return value

    def validate_credentials(self, value):
        if not isinstance(value, dict) or len(json.dumps(value)) > 10000:
            raise serializers.ValidationError("Credentials must be a small JSON object.")
        return json.dumps(value)

    class Meta:
        model = IntegrationConfig
        fields = ["id", "provider", "credentials", "options", "enabled", "is_test", "configured"]
        read_only_fields = ["id", "configured"]


class IntegrationList(generics.ListCreateAPIView):
    serializer_class = IntegrationSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return IntegrationConfig.objects.for_workspace(self.kwargs["workspace_id"]).order_by(
            "provider"
        )

    def perform_create(self, serializer):
        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        data = serializer.validated_data
        from django.conf import settings

        if data.get("is_test") and settings.CHANNEL_ADAPTER_MODE != "fake":
            raise serializers.ValidationError("Test integrations are disabled.")
        item, _ = IntegrationConfig.objects.for_workspace(member.workspace_id).update_or_create(
            workspace=member.workspace,
            provider=data["provider"],
            defaults={key: value for key, value in data.items() if key != "provider"},
        )
        serializer.instance = item
        audit(member.workspace, self.request.user, "integration.configured", item.id)


class SyncLeadView(APIView):
    def post(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        lead = get_object_or_404(Lead.objects.for_workspace(workspace_id), pk=pk)
        provider = request.data.get("provider")
        integration = get_object_or_404(
            IntegrationConfig.objects.for_workspace(workspace_id), provider=provider, enabled=True
        )
        if provider not in {"airtable", "notion", "gohighlevel", "attio"}:
            raise serializers.ValidationError("Choose a CRM integration.")
        job = IntegrationJob.objects.for_workspace(workspace_id).create(
            workspace_id=workspace_id,
            integration=integration,
            operation="sync_lead",
            payload=json.dumps(LeadSerializer(lead).data, default=str),
            idempotency_key="sync:" + str(lead.id) + ":" + secrets.token_hex(8),
            available_at=timezone.now(),
        )
        return Response({"id": job.id}, status=202)
