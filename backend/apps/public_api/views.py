"""Public REST API (`/api/v1/`) for API-key callers, plus in-app key management."""

import secrets

from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crm.models import Conversation, Lead, Message
from apps.crm.services import queue_reply
from apps.crm.views import LeadSerializer
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .auth import APIKeyAuthentication, APIKeyThrottle, HasAPIKey, generate_key
from .models import EVENTS, SCOPES, APIKey, OutboundWebhook, WebhookSubscription
from .services import conversation_payload, emit, lead_payload, message_payload
from .tasks import is_public_https

# ---------- In-app management (session/JWT, owner/admin) ----------


def new_credentials():
    """Both shown exactly once: the HMAC secret and the shared header token."""
    return "whsec_" + secrets.token_urlsafe(32), "whtok_" + secrets.token_urlsafe(32)


class KeySerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ["id", "name", "prefix", "scopes", "last_used_at", "revoked_at", "created_at"]
        read_only_fields = ["id", "prefix", "last_used_at", "revoked_at", "created_at"]

    def validate_scopes(self, value):
        if not value or any(scope not in SCOPES for scope in value):
            raise serializers.ValidationError("Scopes must be read and/or write.")
        return sorted(set(value))


class KeyList(generics.ListCreateAPIView):
    serializer_class = KeySerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return APIKey.objects.for_workspace(self.kwargs["workspace_id"]).filter(
            revoked_at__isnull=True
        )

    def create(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if APIKey.objects.for_workspace(workspace_id).filter(revoked_at__isnull=True).count() >= 20:
            raise serializers.ValidationError("Revoke an unused key first (limit 20).")
        raw, prefix, digest = generate_key()
        key = serializer.save(
            workspace=member.workspace, prefix=prefix, key_hash=digest, created_by=request.user
        )
        audit(member.workspace, request.user, "api_key.created", key.id)
        # The raw key is shown exactly once.
        return Response({**KeySerializer(key).data, "key": raw}, status=201)


class KeyDetail(APIView):
    def delete(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner"])
        key = get_object_or_404(
            APIKey.objects.for_workspace(workspace_id), pk=pk, revoked_at__isnull=True
        )
        key.revoked_at = timezone.now()
        key.save(update_fields=["revoked_at"])
        WebhookSubscription.objects.for_workspace(workspace_id).filter(api_key=key).update(
            active=False
        )
        audit(member.workspace, request.user, "api_key.revoked", key.id)
        return Response(status=204)


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookSubscription
        fields = [
            "id",
            "url",
            "events",
            "active",
            "failure_count",
            "last_delivered_at",
            "created_at",
        ]
        read_only_fields = ["id", "failure_count", "last_delivered_at", "created_at"]

    def validate_url(self, value):
        if not is_public_https(value):
            raise serializers.ValidationError("Use a public HTTPS URL.")
        return value

    def validate_events(self, value):
        if not value or any(event not in EVENTS for event in value):
            raise serializers.ValidationError(f"Events must be from: {', '.join(EVENTS)}.")
        return sorted(set(value))


class SubscriptionList(generics.ListCreateAPIView):
    """In-app view of subscriptions (including ones Zapier created through the API)."""

    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return WebhookSubscription.objects.for_workspace(self.kwargs["workspace_id"])

    def create(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        secret, token = new_credentials()
        item = serializer.save(workspace=member.workspace, secret=secret, token=token)
        audit(member.workspace, request.user, "webhook.subscribed", item.id)
        return Response(
            {**SubscriptionSerializer(item).data, "secret": secret, "token": token}, status=201
        )


class SubscriptionDetail(APIView):
    def delete(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        item = get_object_or_404(WebhookSubscription.objects.for_workspace(workspace_id), pk=pk)
        item.delete()
        audit(member.workspace, request.user, "webhook.unsubscribed", pk)
        return Response(status=204)


class DeliveryLog(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        return Response(
            list(
                OutboundWebhook.objects.for_workspace(workspace_id)
                .order_by("-created_at")
                .values(
                    "id",
                    "subscription_id",
                    "event",
                    "status",
                    "attempts",
                    "response_code",
                    "created_at",
                )[:100]
            )
        )


# ---------- Public v1 (X-API-Key) ----------


class V1View(APIView):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey]
    throttle_classes = [APIKeyThrottle]

    @property
    def workspace_id(self):
        return self.request.user.workspace_id

    def paginate(self, queryset, serialize):
        try:
            limit = max(1, min(int(self.request.query_params.get("limit", 50)), 200))
        except ValueError:
            limit = 50
        cursor = self.request.query_params.get("cursor")
        if cursor:
            # "+00:00" arrives as " 00:00" through query-string decoding.
            parsed = parse_datetime(cursor.replace(" ", "+"))
            if not parsed:
                raise serializers.ValidationError("Invalid cursor.")
            queryset = queryset.filter(created_at__lt=parsed)
        items = list(queryset.order_by("-created_at")[: limit + 1])
        more = len(items) > limit
        items = items[:limit]
        return Response(
            {
                "results": [serialize(item) for item in items],
                "next_cursor": items[-1].created_at.isoformat() if more and items else None,
            }
        )


class V1Me(V1View):
    """Connector auth test: which workspace and scopes does this key have?"""

    def get(self, request):
        key = request.user.api_key
        return Response(
            {
                "workspace": {"id": str(key.workspace_id), "name": key.workspace.name},
                "key": {"name": key.name, "prefix": key.prefix, "scopes": key.scopes},
                "events": EVENTS,
            }
        )


class V1Leads(V1View):
    def get(self, request):
        query = Lead.objects.for_workspace(self.workspace_id)
        email = request.query_params.get("email", "")[:254]
        if email:
            query = query.filter(email__iexact=email)
        if request.query_params.get("stage"):
            query = query.filter(stage=request.query_params["stage"][:20])
        tag = request.query_params.get("tag", "")[:40]
        if tag:
            if connection.vendor == "postgresql":
                query = query.filter(tags__contains=[tag])
            else:
                query = query.filter(pk__in=[lead.pk for lead in query if tag in lead.tags])
        return self.paginate(query, lead_payload)


class V1Lead(V1View):
    def get(self, request, pk):
        lead = get_object_or_404(Lead.objects.for_workspace(self.workspace_id), pk=pk)
        return Response(lead_payload(lead))

    @transaction.atomic
    def patch(self, request, pk):
        lead = get_object_or_404(
            Lead.objects.for_workspace(self.workspace_id).select_for_update(), pk=pk
        )
        serializer = LeadSerializer(lead, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        lead = serializer.save()
        audit(lead.workspace, None, "lead.updated", lead.id)
        emit(self.workspace_id, "lead.updated", lead_payload(lead))
        return Response(lead_payload(lead))


class V1Conversations(V1View):
    def get(self, request):
        query = Conversation.objects.for_workspace(self.workspace_id).select_related(
            "identity__connection"
        )
        if request.query_params.get("lead"):
            query = query.filter(identity__lead_id=request.query_params["lead"])
        if request.query_params.get("status") in {"open", "closed", "needs_human"}:
            query = query.filter(status=request.query_params["status"])
        return self.paginate(query, conversation_payload)


class V1Messages(V1View):
    def get(self, request, pk):
        conversation = get_object_or_404(
            Conversation.objects.for_workspace(self.workspace_id), pk=pk
        )
        return self.paginate(
            Message.objects.for_workspace(self.workspace_id).filter(conversation=conversation),
            message_payload,
        )

    def post(self, request, pk):
        conversation = get_object_or_404(
            Conversation.objects.for_workspace(self.workspace_id), pk=pk
        )
        text = request.data.get("text")
        key = str(request.data.get("idempotency_key", ""))
        if not isinstance(text, str) or not 1 <= len(text) <= 2000 or not 1 <= len(key) <= 100:
            raise serializers.ValidationError(
                "Supply text (1–2000 characters) and an idempotency_key."
            )
        item = queue_reply(conversation, text, f"api:{pk}:{key}")
        return Response({"delivery_id": item.id, "status": item.status}, status=202)


class V1Subscriptions(V1View):
    """REST hooks: Zapier/n8n/Make subscribe here and receive signed POSTs."""

    def get(self, request):
        return Response(
            [
                SubscriptionSerializer(item).data
                for item in WebhookSubscription.objects.for_workspace(self.workspace_id)
            ]
        )

    def post(self, request):
        serializer = SubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        secret, token = new_credentials()
        item = serializer.save(
            workspace_id=self.workspace_id,
            secret=secret,
            token=token,
            api_key=request.user.api_key,
        )
        audit(item.workspace, None, "webhook.subscribed", item.id)
        return Response(
            {**SubscriptionSerializer(item).data, "secret": secret, "token": token}, status=201
        )


class V1Subscription(V1View):
    def delete(self, request, pk):
        item = get_object_or_404(
            WebhookSubscription.objects.for_workspace(self.workspace_id), pk=pk
        )
        item.delete()
        return Response(status=204)


class V1Sample(V1View):
    """Sample payload per event, so Zapier's "perform list" has realistic fields."""

    def get(self, request, event):
        if event not in EVENTS:
            return Response({"detail": "Unknown event."}, status=404)
        lead = Lead.objects.for_workspace(self.workspace_id).first()
        data = lead_payload(lead) if lead else {"id": "…", "name": "Sample lead", "stage": "new"}
        return Response([{"event": event, "workspace_id": str(self.workspace_id), "data": data}])
