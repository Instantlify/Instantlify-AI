import json
import secrets
import uuid

from django.db import transaction
from django.db.models import Count, Max, OuterRef, Prefetch, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.pagination import PageNumberPagination
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
    SavedReply,
)
from .services import notify, queue_reply


def conversations_for(request, workspace_id, *, allow_viewer_write=False):
    member = workspace_membership(request, workspace_id, allow_viewer_write=allow_viewer_write)
    query = Conversation.objects.for_workspace(workspace_id)
    if member.role == "agent":
        query = query.filter(Q(assigned_to=request.user) | Q(assigned_to__isnull=True))
    from apps.tenants.access import connection_ids

    allowed = connection_ids(member)
    if allowed is not None:
        query = query.filter(identity__connection_id__in=allowed)
    return query.select_related("identity__lead", "identity__connection")


class ConversationSerializer(serializers.ModelSerializer):
    lead = serializers.SerializerMethodField()
    provider = serializers.CharField(source="identity.connection.provider", read_only=True)
    is_test = serializers.BooleanField(source="identity.connection.is_test", read_only=True)
    connection_id = serializers.UUIDField(source="identity.connection_id", read_only=True)
    connection_name = serializers.CharField(
        source="identity.connection.display_name", read_only=True
    )
    contact_link = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread = serializers.SerializerMethodField()
    seen_by = serializers.SerializerMethodField()

    def get_unread(self, obj):
        reads = self.context.get("reads")
        if reads is None or not obj.last_inbound_at:
            return False
        mine = reads.get(obj.pk, {}).get(self.context.get("user_id"))
        return mine is None or mine < obj.last_inbound_at

    def get_seen_by(self, obj):
        reads = self.context.get("reads") or {}
        names = self.context.get("names") or {}
        latest = max((t for t in (obj.last_inbound_at, obj.last_outbound_at) if t), default=None)
        return [
            names[user_id]
            for user_id, read_at in reads.get(obj.pk, {}).items()
            if user_id != self.context.get("user_id")
            and user_id in names
            and (latest is None or read_at >= latest)
        ]

    def get_contact_link(self, obj):
        return contact_link(obj.identity)

    def get_last_message(self, obj):
        return self.context.get("snippets", {}).get(obj.pk)

    def get_lead(self, obj):
        lead = obj.identity.lead
        return {
            "id": lead.id,
            "name": lead.name,
            "handle": lead.handle,
            "avatar_url": lead.avatar_url,
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
            "handoff_reason",
            "last_inbound_at",
            "last_outbound_at",
            "updated_at",
            "connection_id",
            "connection_name",
            "contact_link",
            "last_message",
            "unread",
            "seen_by",
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
        provider = self.request.query_params.get("provider", "")[:30]
        if provider:
            query = query.filter(identity__connection__provider=provider)
        connection = self.request.query_params.get("connection", "")
        if connection:
            try:
                query = query.filter(identity__connection_id=uuid.UUID(connection))
            except ValueError:
                raise serializers.ValidationError("Invalid connection.") from None
        return query.annotate(
            last_message_id=Subquery(
                Message.objects.for_workspace(self.kwargs["workspace_id"])
                .filter(conversation=OuterRef("pk"))
                .order_by("-created_at", "-sequence", "-id")
                .values("pk")[:1]
            )
        )

    def get_serializer(self, *args, **kwargs):
        # Message text is encrypted at rest, so the page's previews are one bulk read.
        if args and isinstance(args[0], list):
            ids = [item.last_message_id for item in args[0] if item.last_message_id]
            snippets = {
                message.conversation_id: {
                    "text": message.text[:140],
                    "kind": message.kind,
                    "direction": message.direction,
                    "created_at": message.created_at,
                }
                for message in Message.objects.for_workspace(self.kwargs["workspace_id"]).filter(
                    pk__in=ids
                )
            }
            from .models import ConversationRead

            reads = {}
            for read in ConversationRead.objects.for_workspace(self.kwargs["workspace_id"]).filter(
                conversation_id__in=[item.pk for item in args[0]]
            ):
                reads.setdefault(read.conversation_id, {})[read.user_id] = read.read_at
            names = {
                member.user_id: member.user.get_full_name() or member.user.username
                for member in Membership.objects.for_workspace(
                    self.kwargs["workspace_id"]
                ).select_related("user")
            }
            kwargs["context"] = {
                **self.get_serializer_context(),
                "snippets": snippets,
                "reads": reads,
                "names": names,
                "user_id": self.request.user.id,
            }
        return super().get_serializer(*args, **kwargs)


class ConversationReadView(APIView):
    """Mark the conversation read by the current teammate."""

    def post(self, request, workspace_id, pk):
        from .models import ConversationRead

        conversation = get_object_or_404(
            conversations_for(request, workspace_id, allow_viewer_write=True), pk=pk
        )
        ConversationRead.objects.for_workspace(workspace_id).update_or_create(
            conversation=conversation,
            user=request.user,
            defaults={"workspace_id": conversation.workspace_id, "read_at": timezone.now()},
        )
        return Response(status=204)


class ConversationDetail(APIView):
    def get(self, request, workspace_id, pk):
        conversation = get_object_or_404(conversations_for(request, workspace_id), pk=pk)
        return Response(ConversationSerializer(conversation).data)

    @transaction.atomic
    def patch(self, request, workspace_id, pk):
        conversation = get_object_or_404(
            conversations_for(request, workspace_id).select_for_update(), pk=pk
        )
        member = workspace_membership(request, workspace_id)
        if "assigned_to" in request.data:
            previous_assignee = conversation.assigned_to_id
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
            from .notifications import assignment_changed

            assignment_changed(conversation.identity.lead, user_id, previous_assignee, request.user)
        if "status" in request.data:
            if request.data["status"] not in {"open", "closed", "needs_human"}:
                raise serializers.ValidationError("Invalid conversation status.")
            conversation.status = request.data["status"]
            if conversation.status != "needs_human":
                conversation.handoff_reason = ""
        if "ai_enabled" in request.data:
            if not isinstance(request.data["ai_enabled"], bool):
                raise serializers.ValidationError("ai_enabled must be boolean.")
            conversation.ai_enabled = request.data["ai_enabled"]
        conversation.save()
        audit(conversation.workspace, request.user, "conversation.updated", conversation.id)
        transaction.on_commit(lambda: notify(workspace_id))
        return Response(ConversationSerializer(conversation).data)


# Who produced an outbound message, read from the delivery's idempotency-key prefix,
# which every sending path sets (see the queue_reply callers).
SENDER_PREFIXES = {
    "agent-reply": "ai",
    "voice": "ai",
    "handoff": "ai",
    "flow": "automation",
    "broadcast": "human",
    "human": "human",
    "payment": "human",
    "api": "api",
    "mcp": "api",
}


class MessageSerializer(serializers.ModelSerializer):
    media_url = serializers.SerializerMethodField()
    delivery_status = serializers.CharField(source="delivery.status", default=None, read_only=True)
    provider_status = serializers.CharField(
        source="delivery.provider_status", default="", read_only=True
    )
    sender = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()

    def get_media_url(self, obj):
        if (
            obj.direction != "outbound"
            or obj.kind not in {"image", "video", "audio"}
            or not obj.delivery
        ):
            return ""
        from apps.channels.media import validate_media

        try:
            payload = json.loads(obj.delivery.payload)
            validate_media(payload.get("media_url"), obj.kind)
            return payload["media_url"]
        except (ValueError, TypeError, serializers.ValidationError):
            return ""

    def get_sender(self, obj):
        if obj.direction == "inbound":
            return "customer"
        if obj.author_id:
            return "human"
        key = obj.delivery.idempotency_key if obj.delivery else ""
        return SENDER_PREFIXES.get(key.split(":", 1)[0], "human")

    def get_author_name(self, obj):
        author = obj.author
        return (author.first_name or author.email) if author else ""

    class Meta:
        model = Message
        fields = [
            "id",
            "sequence",
            "direction",
            "text",
            "kind",
            "created_at",
            "delivery_status",
            "provider_status",
            "sender",
            "author_name",
            "media_url",
        ]


class MessageList(generics.ListAPIView):
    serializer_class = MessageSerializer

    def get_queryset(self):
        conversation = get_object_or_404(
            conversations_for(self.request, self.kwargs["workspace_id"]), pk=self.kwargs["pk"]
        )
        return (
            Message.objects.for_workspace(conversation.workspace_id)
            .filter(conversation=conversation)
            .select_related("delivery", "author")
            .order_by("-created_at", "-sequence", "-id")
        )

    def post(self, request, workspace_id, pk):
        conversation = get_object_or_404(conversations_for(request, workspace_id), pk=pk)
        upload = request.FILES.get("file")
        text = request.data.get("text") or ""
        key = request.headers.get("Idempotency-Key", "")
        if (
            not isinstance(text, str)
            or len(text) > 2000
            or not (text.strip() or upload)
            or not 1 <= len(key) <= 100
        ):
            raise serializers.ValidationError(
                "Supply text (1–2000 characters) or a file, and an Idempotency-Key."
            )
        if upload:
            return self._send_attachment(request, conversation, upload, text.strip(), key)
        item = queue_reply(conversation, text, f"human:{pk}:{key}", actor=request.user)
        return Response({"id": item.id, "status": item.status}, status=202)

    @staticmethod
    def _send_attachment(request, conversation, upload, caption, key):
        from apps.channels.media import MEDIA_CHANNELS
        from apps.channels.models import Delivery

        from .attachments import attachment_url, can_deliver_by_url, store_attachment

        connection = conversation.identity.connection
        if connection.provider not in MEDIA_CHANNELS:
            raise serializers.ValidationError("This channel cannot receive files.")
        pk = conversation.pk
        file_key = f"human:{pk}:{key}:file"
        with transaction.atomic():
            existing = (
                Delivery.objects.for_workspace(conversation.workspace_id)
                .filter(idempotency_key=file_key)
                .first()
            )
            if existing:
                # A retried request must not store the file a second time.
                return Response({"id": existing.id, "status": existing.status}, status=202)
            attachment, kind = store_attachment(conversation, upload)
            if can_deliver_by_url():
                item = queue_reply(
                    conversation,
                    "",
                    file_key,
                    actor=request.user,
                    media_url=attachment_url(attachment),
                    media_type=kind,
                )
            elif connection.is_test:
                # Local test channels never reach a provider; record what would be sent.
                item = queue_reply(
                    conversation,
                    f"[Local test {kind}: {attachment.filename}]",
                    file_key,
                    actor=request.user,
                )
            else:
                raise serializers.ValidationError(
                    "Sending files needs a public HTTPS app address (PUBLIC_APP_URL)."
                )
            # Media messages carry no caption on every channel, so the text follows.
            if caption:
                item = queue_reply(conversation, caption, f"human:{pk}:{key}", actor=request.user)
        return Response({"id": item.id, "status": item.status}, status=202)


class SavedRepliesView(APIView):
    """The team's shared quick replies. PUT replaces the whole ordered list, which is
    how the composer edits it (add, delete), so there is no partial-update drift."""

    MAX_REPLIES = 50

    def _list(self, workspace_id):
        return list(SavedReply.objects.for_workspace(workspace_id).values_list("text", flat=True))

    def get(self, request, workspace_id):
        member = workspace_membership(request, workspace_id)
        return Response({"replies": self._list(member.workspace_id)})

    def put(self, request, workspace_id):
        member = workspace_membership(request, workspace_id)
        replies = request.data.get("replies")
        if (
            not isinstance(replies, list)
            or len(replies) > self.MAX_REPLIES
            or not all(isinstance(item, str) and 1 <= len(item.strip()) <= 1000 for item in replies)
        ):
            raise serializers.ValidationError(
                f"Send up to {self.MAX_REPLIES} replies of 1–1000 characters each."
            )
        cleaned = list(dict.fromkeys(item.strip() for item in replies))
        workspace = member.workspace
        with transaction.atomic():
            Workspace.objects.select_for_update().get(pk=workspace.pk)
            SavedReply.objects.for_workspace(workspace).delete()
            SavedReply.objects.for_workspace(workspace).bulk_create(
                [
                    SavedReply(workspace=workspace, text=text, position=index)
                    for index, text in enumerate(cleaned)
                ]
            )
        audit(workspace, request.user, "saved_replies.updated", workspace.pk)
        return Response({"replies": cleaned})


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


class ConversationEventsView(APIView):
    """System milestones in a thread (flow triggered, handoff, booking, payment) for
    the inbox timeline, read from the append-only funnel trail."""

    KINDS = ["triggered", "handoff", "link_click", "booked", "paid"]

    def get(self, request, workspace_id, pk):
        from apps.analytics.models import FunnelEvent
        from apps.automations.models import Automation

        conversation = get_object_or_404(conversations_for(request, workspace_id), pk=pk)
        events = list(
            FunnelEvent.objects.for_workspace(workspace_id)
            .filter(conversation_id=conversation.pk, kind__in=self.KINDS)
            .order_by("created_at", "id")
            .values("id", "kind", "automation_id", "amount_cents", "created_at")[:200]
        )
        names = dict(
            Automation.objects.for_workspace(workspace_id)
            .filter(pk__in={event["automation_id"] for event in events} - {None})
            .values_list("pk", "name")
        )
        for event in events:
            event["automation_name"] = names.get(event.pop("automation_id"), "")
        return Response(events)


class LeadSerializer(serializers.ModelSerializer):
    assigned_to = serializers.IntegerField(
        source="assigned_to_id", required=False, allow_null=True, min_value=1
    )

    class Meta:
        model = Lead
        fields = [
            "id",
            "name",
            "handle",
            "avatar_url",
            "email",
            "assigned_to",
            "stage",
            "tags",
            "fields",
            "opted_out",
            "profile_synced_at",
            "created_at",
            "ai_summary",
            "ai_summary_at",
        ]
        read_only_fields = [
            "id",
            "avatar_url",
            "profile_synced_at",
            "created_at",
            "ai_summary",
            "ai_summary_at",
        ]

    def validate_assigned_to(self, value):
        request = self.context.get("request")
        view = self.context.get("view")
        if not request or not view:
            raise serializers.ValidationError("Assign contacts through the workspace contact API.")
        workspace_id = view.kwargs["workspace_id"]
        workspace_membership(request, workspace_id, ["owner", "admin"])
        if (
            value is not None
            and not Membership.objects.for_workspace(workspace_id)
            .filter(user_id=value, user__is_active=True, user__is_banned=False)
            .exists()
        ):
            raise serializers.ValidationError("Assignee must be an active workspace member.")
        return value

    def validate_stage(self, value):
        from .stages import validate_stage_for

        view = self.context.get("view")
        return validate_stage_for(view.kwargs["workspace_id"] if view else None, value)

    def validate_tags(self, value):
        if not isinstance(value, list) or len(value) > 50:
            raise serializers.ValidationError("Tags must be a list of up to 50 entries.")
        tags = []
        for tag in value:
            if not isinstance(tag, str) or not 1 <= len(tag.strip()) <= 40:
                raise serializers.ValidationError("Each tag needs 1–40 characters.")
            if tag.strip() not in tags:
                tags.append(tag.strip())
        return tags

    def validate_fields(self, value):
        if (
            not isinstance(value, dict)
            or len(value) > 50
            or any(
                not isinstance(key, str) or not 1 <= len(key) <= 60 or len(str(item)) > 500
                for key, item in value.items()
            )
        ):
            raise serializers.ValidationError("Fields must be a small map of short values.")
        view = self.context.get("view")
        if view:
            from .field_defs import coerce_fields

            value = coerce_fields(view.kwargs["workspace_id"], value)
        return value


def contact_link(identity):
    # WhatsApp identities are phone numbers; other channels use opaque scoped IDs.
    if identity.connection.provider == "whatsapp":
        digits = "".join(ch for ch in identity.external_id if ch.isdigit())
        return f"https://wa.me/{digits}" if digits else ""
    return ""


class LeadRowSerializer(LeadSerializer):
    """A CRM table row: the lead plus where it came from and who is working it."""

    channels = serializers.SerializerMethodField()
    identities = serializers.SerializerMethodField()
    conversation_id = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()
    message_count = serializers.IntegerField(read_only=True)
    last_activity_at = serializers.DateTimeField(read_only=True, default=None)

    def _conversations(self, obj):
        return [
            identity.conversation
            for identity in obj.identities
            if getattr(identity, "conversation", None) is not None
        ]

    def get_channels(self, obj):
        return sorted({identity.connection.provider for identity in obj.identities})

    def get_identities(self, obj):
        return [
            {
                "id": identity.id,
                "provider": identity.connection.provider,
                "connection_id": identity.connection_id,
                "connection_name": identity.connection.display_name,
                "external_id": identity.external_id,
                "conversation_id": getattr(identity, "conversation", None)
                and identity.conversation.pk,
                "contact_link": contact_link(identity),
            }
            for identity in obj.identities
        ]

    def get_conversation_id(self, obj):
        conversations = self._conversations(obj)
        return max(conversations, key=lambda item: item.updated_at).pk if conversations else None

    def get_assigned_to(self, obj):
        if obj.assigned_to_id is not None:
            return obj.assigned_to_id
        conversations = self._conversations(obj)
        if not conversations:
            return None
        return max(conversations, key=lambda item: item.updated_at).assigned_to_id

    class Meta(LeadSerializer.Meta):
        fields = LeadSerializer.Meta.fields + [
            "channels",
            "identities",
            "conversation_id",
            "message_count",
            "last_activity_at",
        ]
        read_only_fields = fields


class LeadPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def visible_leads(request, workspace_id):
    """Leads the caller may edit. Managers see every contact, including ones added by
    hand; agents see their assigned contacts and contacts behind visible conversations."""
    member = workspace_membership(request, workspace_id)
    query = Lead.objects.for_workspace(workspace_id)
    from apps.tenants.access import connection_ids

    if member.role == "agent" or connection_ids(member) is not None:
        # Limited members see contacts behind the conversations they can open, plus
        # contacts assigned to them.
        ids = conversations_for(request, workspace_id).values_list("identity__lead_id", flat=True)
        query = query.filter(Q(assigned_to=request.user) | Q(pk__in=ids))
    return query


def lead_rows(query, workspace_id):
    """Annotate and prefetch what LeadRowSerializer renders."""
    return (
        query.annotate(
            message_count=Count("channelidentity__conversation__message", distinct=True),
            last_activity_at=Max("channelidentity__conversation__updated_at"),
        )
        # Grouped queries drop Meta.ordering; pagination needs a stable order.
        .order_by("-created_at", "-id")
        .prefetch_related(
            Prefetch(
                "channelidentity_set",
                queryset=ChannelIdentity.objects.for_workspace(workspace_id).select_related(
                    "connection", "conversation"
                ),
                to_attr="identities",
            )
        )
    )


class LeadList(generics.ListCreateAPIView):
    serializer_class = LeadRowSerializer
    pagination_class = LeadPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return LeadSerializer
        return LeadRowSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        # A contact added by hand: no channel identity or conversation until the
        # person actually messages one of the workspace's channels.
        member = workspace_membership(self.request, self.kwargs["workspace_id"])
        from apps.billing.gating import check_within_limit
        from apps.tenants.models import Workspace

        Workspace.objects.select_for_update().get(pk=member.workspace_id)
        check_within_limit(member.workspace_id, "max_contacts")
        serializer.save(workspace=member.workspace)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        lead = serializer.instance
        audit(lead.workspace, self.request.user, "lead.created", lead.id)
        # A new contact has no channel identities yet, so nothing to count.
        lead.identities = []
        lead.message_count = 0
        lead.last_activity_at = None
        return Response(LeadRowSerializer(lead).data, status=201)

    def get_queryset(self):
        workspace_id = self.kwargs["workspace_id"]
        query = visible_leads(self.request, workspace_id)
        params = self.request.query_params
        search = params.get("search", "")[:100]
        if search:
            query = query.filter(
                Q(name__icontains=search) | Q(email__icontains=search) | Q(handle__icontains=search)
            )
        if params.get("stage"):
            query = query.filter(stage=params["stage"][:20])
        if params.get("tag"):
            query = query.filter(tags__icontains=params["tag"][:40])
        if params.get("provider"):
            query = query.filter(
                pk__in=ChannelIdentity.objects.for_workspace(workspace_id)
                .filter(connection__provider=params["provider"][:30])
                .values("lead_id")
            )
        elif params.get("source") == "channel":
            query = query.filter(channelidentity__isnull=False).distinct()
        elif params.get("source") == "manual":
            query = query.filter(channelidentity__isnull=True).filter(
                Q(fields__source__isnull=True) | ~Q(fields__source="form")
            )
        elif params.get("source") == "form":
            query = query.filter(fields__source="form")
        return lead_rows(query, workspace_id)


class LeadIdsSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=200)


class LeadBulkView(APIView):
    """Apply a tag or a stage to many leads at once, with the same visibility and
    side effects (audit, lead.updated webhook) as editing each lead."""

    @transaction.atomic
    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id)
        body = LeadIdsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        action = request.data.get("action")
        value = request.data.get("value")
        if action == "stage":
            if not isinstance(value, str):
                raise serializers.ValidationError("Invalid stage.")
            from .stages import validate_stage_for

            value = validate_stage_for(workspace_id, value)
        elif action in {"tag", "untag"}:
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 40:
                raise serializers.ValidationError("A tag needs 1–40 characters.")
            value = value.strip()
        else:
            raise serializers.ValidationError("Choose a bulk action.")
        from apps.public_api.services import emit, lead_payload

        leads = list(
            visible_leads(request, workspace_id)
            .filter(pk__in=body.validated_data["ids"])
            .select_for_update()
        )
        for lead in leads:
            if action == "stage":
                lead.stage = value
            elif action == "tag" and value not in lead.tags:
                lead.tags = [*lead.tags, value]
            elif action == "untag":
                lead.tags = [tag for tag in lead.tags if tag != value]
            lead.save(update_fields=["stage", "tags"])
            audit(member.workspace, request.user, "lead.updated", lead.id)
            emit(workspace_id, "lead.updated", lead_payload(lead))
        return Response({"updated": len(leads)})


class LeadBroadcastView(APIView):
    """Send one message to selected leads. Meta only allows free-form messages inside
    the 24-hour customer-service window, so leads outside it are skipped, not queued."""

    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        body = LeadIdsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        text = request.data.get("text")
        key = request.headers.get("Idempotency-Key", "")
        if (
            not isinstance(text, str)
            or not 1 <= len(text.strip()) <= 2000
            or not 1 <= len(key) <= 100
        ):
            raise serializers.ValidationError(
                "Supply text (1–2000 characters) and an Idempotency-Key."
            )
        conversations = conversations_for(request, workspace_id).filter(
            identity__lead_id__in=body.validated_data["ids"]
        )
        queued = skipped = 0
        for conversation in conversations:
            try:
                queue_reply(
                    conversation,
                    text.strip(),
                    f"broadcast:{key}:{conversation.pk}",
                    actor=request.user,
                )
                queued += 1
            except serializers.ValidationError:
                skipped += 1
        audit(member.workspace, request.user, "leads.broadcast", workspace_id)
        return Response({"queued": queued, "skipped": skipped})


class LeadDetail(generics.RetrieveUpdateDestroyAPIView):
    """One contact with its channels and conversations. Reads and updates answer in
    the row shape the CRM renders, so the panel never needs a second request."""

    serializer_class = LeadSerializer

    def get_queryset(self):
        return lead_rows(
            visible_leads(self.request, self.kwargs["workspace_id"]), self.kwargs["workspace_id"]
        )

    def retrieve(self, request, *args, **kwargs):
        return Response(LeadRowSerializer(self.get_object()).data)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(LeadRowSerializer(self.get_object()).data)

    def perform_update(self, serializer):
        from apps.public_api.services import emit, lead_payload

        previous_assignee = serializer.instance.assigned_to_id
        lead = serializer.save()
        if "assigned_to_id" in serializer.validated_data:
            from .notifications import assignment_changed

            assignment_changed(lead, lead.assigned_to_id, previous_assignee, self.request.user)
            Conversation.objects.for_workspace(lead.workspace_id).filter(
                identity__lead=lead
            ).update(assigned_to_id=lead.assigned_to_id)
            transaction.on_commit(lambda: notify(lead.workspace_id))
        audit(lead.workspace, self.request.user, "lead.updated", lead.id)
        emit(lead.workspace_id, "lead.updated", lead_payload(lead))

    def perform_destroy(self, lead):
        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        audit(member.workspace, self.request.user, "lead.deleted", lead.id)
        lead.delete()


class RefreshLeadView(APIView):
    """Re-read the person's name, handle and photo from their channel right now."""

    def post(self, request, workspace_id, pk):
        from .services import sync_profile

        workspace_membership(request, workspace_id, ["owner", "admin"])
        lead = get_object_or_404(visible_leads(request, workspace_id), pk=pk)
        if not ChannelIdentity.objects.for_workspace(workspace_id).filter(lead=lead).exists():
            raise serializers.ValidationError(
                "This contact has not messaged any connected channel yet."
            )
        from apps.channels.transport import ProviderError

        try:
            sync_profile(lead)
        except ProviderError:
            raise serializers.ValidationError(
                "The channel did not return a profile. Try again in a moment."
            ) from None
        row = get_object_or_404(
            lead_rows(visible_leads(request, workspace_id), workspace_id), pk=pk
        )
        return Response(LeadRowSerializer(row).data)


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
        target.email = target.email or source.email
        target.handle = target.handle or source.handle
        target.avatar_url = target.avatar_url or source.avatar_url
        target.assigned_to_id = target.assigned_to_id or source.assigned_to_id
        if target.assigned_to_id:
            Conversation.objects.for_workspace(workspace_id).filter(identity__lead=target).update(
                assigned_to_id=target.assigned_to_id
            )
        # A typed name beats a raw channel ID left by a contact that was never enriched.
        if (
            target.name
            in {
                "",
                *ChannelIdentity.objects.for_workspace(workspace_id)
                .filter(lead=target)
                .values_list("external_id", flat=True),
            }
            and source.name
        ):
            target.name = source.name
        target.save(
            update_fields=[
                "tags",
                "opted_out",
                "fields",
                "email",
                "handle",
                "avatar_url",
                "name",
                "assigned_to",
            ]
        )
        source.delete()
        audit(member.workspace, request.user, "leads.merged", target.id)
        row = get_object_or_404(
            lead_rows(visible_leads(request, workspace_id), workspace_id), pk=pk
        )
        return Response(LeadRowSerializer(row).data)


class IntegrationSerializer(serializers.ModelSerializer):
    # Omitting credentials (or sending {}) on re-save keeps the stored secret.
    credentials = serializers.JSONField(write_only=True, required=False)
    configured = serializers.SerializerMethodField()

    def get_configured(self, obj):
        return bool(json.loads(obj.credentials)) or obj.is_test

    def validate_provider(self, value):
        if value not in {
            "google_calendar",
            "google_sheets",
            "gmail",
            "outlook",
            "zorromail",
            "mailerlite",
            "klaviyo",
            "mailchimp",
            "beehiiv",
            "kit",
            "shopify",
            "systeme_io",
            "jotform",
            "calcom",
            "airtable",
            "notion",
            "gohighlevel",
            "attio",
            "slack",
            "elevenlabs",
            "inworld",
            "minimax",
            "vapi",
            "retell",
            "heygen",
            "stripe",
            "n8n",
            "make",
            "discord",
            "webhook",
        }:
            raise serializers.ValidationError("Unsupported provider.")
        return value

    def validate_credentials(self, value):
        if not isinstance(value, dict) or len(json.dumps(value)) > 10000:
            raise serializers.ValidationError("Credentials must be a small JSON object.")
        if any(not isinstance(item, str) for item in value.values()):
            raise serializers.ValidationError("Credential values must be text.")
        if "authorization" in value and (
            not isinstance(value["authorization"], str)
            or "\r" in value["authorization"]
            or "\n" in value["authorization"]
        ):
            raise serializers.ValidationError("Authorization must be a single header value.")
        if "webhook_url" in value and value["webhook_url"]:
            from apps.channels.transport import ProviderError
            from apps.public_api.outbound import endpoint_parts

            try:
                endpoint_parts(value["webhook_url"])
            except ProviderError:
                raise serializers.ValidationError(
                    "Use a complete HTTPS webhook URL without credentials or fragments."
                ) from None
        return json.dumps(value)

    def validate_options(self, value):
        if not isinstance(value, dict) or len(json.dumps(value)) > 10000:
            raise serializers.ValidationError("Options must be a small JSON object.")
        if set(value) & {
            "api_key",
            "access_token",
            "refresh_token",
            "client_secret",
            "bot_token",
            "secret_key",
            "webhook_url",
            "authorization",
            "webhook_secret",
            "password",
        }:
            raise serializers.ValidationError("Store secrets in credentials, not public options.")
        return value

    class Meta:
        model = IntegrationConfig
        fields = [
            "id",
            "provider",
            "credentials",
            "options",
            "enabled",
            "is_test",
            "configured",
            "status",
        ]
        read_only_fields = ["id", "configured", "status"]


class IntegrationList(generics.ListCreateAPIView):
    serializer_class = IntegrationSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return IntegrationConfig.objects.for_workspace(self.kwargs["workspace_id"]).order_by(
            "provider"
        )

    def perform_create(self, serializer):
        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        from django.conf import settings

        from apps.billing.gating import check_feature

        check_feature(member.workspace_id, "integrations_unlocked")
        data = serializer.validated_data

        if data.get("is_test") and settings.CHANNEL_ADAPTER_MODE != "fake":
            raise serializers.ValidationError("Test integrations are disabled.")
        defaults = {key: value for key, value in data.items() if key != "provider"}
        if defaults.get("credentials", "{}") == "{}":
            defaults.pop("credentials", None)
        existing = (
            IntegrationConfig.objects.for_workspace(member.workspace_id)
            .filter(provider=data["provider"])
            .first()
        )
        if existing and "credentials" in defaults:
            defaults["credentials"] = json.dumps(
                {**json.loads(existing.credentials), **json.loads(defaults["credentials"])}
            )
        if existing and "options" in defaults:
            defaults["options"] = {**existing.options, **defaults["options"]}
        if not data.get("is_test", existing.is_test if existing else False):
            from .configuration import validate_live_configuration

            validate_live_configuration(
                data["provider"],
                json.loads(defaults.get("credentials", existing.credentials if existing else "{}")),
                defaults.get("options", existing.options if existing else {}),
            )
        if not existing and "credentials" not in defaults and not data.get("is_test"):
            raise serializers.ValidationError("Enter the provider credentials.")
        if "credentials" in defaults or data.get("is_test"):
            # Fresh credentials clear a reconnect flag; saving options alone does not.
            defaults["status"] = "active"
        if data["provider"] in {"n8n", "make", "discord", "webhook"} and not data.get(
            "is_test", existing.is_test if existing else False
        ):
            configured = json.loads(
                defaults.get("credentials", existing.credentials if existing else "{}")
            )
            if not configured.get("webhook_url"):
                raise serializers.ValidationError("Enter the webhook URL.")
        item, _ = IntegrationConfig.objects.for_workspace(member.workspace_id).update_or_create(
            workspace=member.workspace,
            provider=data["provider"],
            defaults=defaults,
        )
        serializer.instance = item
        audit(member.workspace, self.request.user, "integration.configured", item.id)


class IntegrationDetail(APIView):
    def delete(self, request, workspace_id, pk):
        """Disconnect: revoke remotely when possible, then drop the stored credentials.
        The row and its job history remain so past bookings/syncs stay auditable."""
        from .oauth import revoke

        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        item = get_object_or_404(IntegrationConfig.objects.for_workspace(workspace_id), pk=pk)
        revoke(item)
        item.credentials = "{}"
        item.enabled = False
        item.is_test = False
        item.status = "disconnected"
        item.save()
        audit(member.workspace, request.user, "integration.disconnected", item.id)
        return Response(IntegrationSerializer(item).data)


class SyncLeadView(APIView):
    def post(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        lead = get_object_or_404(Lead.objects.for_workspace(workspace_id), pk=pk)
        provider = request.data.get("provider")
        integration = get_object_or_404(
            IntegrationConfig.objects.for_workspace(workspace_id), provider=provider, enabled=True
        )
        if provider not in {
            "airtable",
            "notion",
            "gohighlevel",
            "attio",
            "google_sheets",
            "mailerlite",
            "klaviyo",
            "systeme_io",
            "mailchimp",
            "beehiiv",
            "kit",
        }:
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
