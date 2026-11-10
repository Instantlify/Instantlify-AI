import base64
import json

from django.conf import settings
from rest_framework import generics, serializers
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gating import check_feature
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import (
    AgentConfig,
    AgentRun,
    KnowledgeBase,
    KnowledgeDocument,
    ToolCall,
    UsageRecord,
)
from .tools import SCHEMAS


class AgentSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_key = serializers.SerializerMethodField()
    embedding_api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_embedding_key = serializers.SerializerMethodField()
    segmentation_prompt = serializers.CharField(max_length=6000, required=False, allow_blank=True)

    def get_has_key(self, obj):
        return bool(obj.api_key)

    def get_has_embedding_key(self, obj):
        return bool(obj.embedding_api_key)

    def validate(self, attrs):
        from .providers import PROVIDERS

        def current(name, default):
            # Partial updates validate against the saved value for anything not sent.
            return attrs.get(name, getattr(self.instance, name, default))

        if not attrs.get("embedding_api_key"):
            attrs.pop("embedding_api_key", None)  # blank means "keep the saved key"
        provider = current("provider", "openai")
        if provider not in PROVIDERS:
            raise serializers.ValidationError("Provider must be OpenAI, Anthropic, Gemini or xAI.")
        fallback = current("fallback_provider", "")
        if fallback:
            if fallback not in PROVIDERS or fallback == provider:
                raise serializers.ValidationError("The fallback must be a different provider.")
            if not current("fallback_model", "").strip():
                raise serializers.ValidationError("Choose a model for the fallback provider.")
            if current("billing_mode", "platform_credits") != "platform_credits":
                # A BYO key covers one vendor; a fallback would run on Nemio's key.
                raise serializers.ValidationError("A fallback provider needs Nemio credits.")
        if attrs.get("is_test") and settings.CHANNEL_ADAPTER_MODE != "fake":
            raise serializers.ValidationError("Test providers are disabled.")
        if any(name not in SCHEMAS for name in attrs.get("allowed_tools", [])):
            raise serializers.ValidationError("Unsupported tool.")
        for name in ["input_cost_per_million", "output_cost_per_million"]:
            if attrs.get(name, 0) < 0:
                raise serializers.ValidationError("Token prices cannot be negative.")
        fields = attrs.get("qualifying_fields", [])
        if any(field not in {"interest", "budget", "timeline", "company"} for field in fields):
            raise serializers.ValidationError(
                "Qualifying fields: interest, budget, timeline, company."
            )
        keywords = attrs.get("handoff_keywords", [])
        if len(keywords) > 30 or any(
            not isinstance(k, str) or not 1 <= len(k) <= 40 for k in keywords
        ):
            raise serializers.ValidationError("Up to 30 handoff keywords of 1–40 characters.")
        if not 1 <= attrs.get("max_tool_rounds", 4) <= 8:
            raise serializers.ValidationError("Tool rounds must be 1–8.")
        if not 0 <= attrs.get("reply_delay_seconds", 0) <= 30:
            raise serializers.ValidationError("The reply delay must be 0–30 seconds.")
        if attrs.get("mode", "agent") not in {"agent", "simple"}:
            raise serializers.ValidationError("Mode must be agent or simple.")
        if attrs.get("billing_mode", "platform_credits") not in {"platform_credits", "byo_key"}:
            raise serializers.ValidationError("Billing mode must be platform_credits or byo_key.")
        return attrs

    class Meta:
        model = AgentConfig
        fields = [
            "id",
            "name",
            "system_prompt",
            "provider",
            "model",
            "api_key",
            "has_key",
            "embedding_model",
            "embedding_api_key",
            "has_embedding_key",
            "fallback_provider",
            "fallback_model",
            "allowed_tools",
            "enabled",
            "is_test",
            "input_cost_per_million",
            "output_cost_per_million",
            "qualifying_fields",
            "segmentation_enabled",
            "segmentation_prompt",
            "triage_enabled",
            "handoff_keywords",
            "max_tool_rounds",
            "reply_delay_seconds",
            "mode",
            "billing_mode",
        ]
        read_only_fields = ["id", "has_key", "has_embedding_key"]


class AgentView(APIView):
    def get(self, request, workspace_id):
        from .catalog import get_platform_models

        workspace_membership(request, workspace_id, ["owner", "admin"])
        config = AgentConfig.objects.for_workspace(workspace_id).first()
        data = AgentSerializer(config).data if config else {}
        data["available_models"] = get_platform_models()
        return Response(data)

    def put(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        check_feature(workspace_id, "ai_agent_enabled")
        config = AgentConfig.objects.for_workspace(workspace_id).first()
        serializer = AgentSerializer(config, data=request.data, partial=bool(config))
        serializer.is_valid(raise_exception=True)
        config = serializer.save(workspace=member.workspace)
        audit(member.workspace, request.user, "agent.configured", config.id)
        data = serializer.data
        from .catalog import get_platform_models

        data["available_models"] = get_platform_models()
        return Response(data)


class AgentModelsView(APIView):
    """List curated platform models with live pricing rates from the rate card."""

    def get(self, request, workspace_id):
        from .catalog import get_platform_models

        workspace_membership(request, workspace_id, ["owner", "admin"])
        return Response(get_platform_models())


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeDocument
        fields = [
            "id",
            "title",
            "status",
            "error_code",
            "embedding_model",
            "created_at",
            "knowledge_base",
            "file_type",
        ]


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeBase
        fields = ["id", "name", "description", "document_count", "created_at"]
        read_only_fields = ["id", "document_count", "created_at"]

    def get_document_count(self, obj):
        return (
            KnowledgeDocument.objects.for_workspace(obj.workspace_id)
            .filter(knowledge_base=obj)
            .count()
        )

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name the knowledge base.")
        return value.strip()


class KnowledgeBaseList(generics.ListCreateAPIView):
    serializer_class = KnowledgeBaseSerializer
    pagination_class = None

    def get_queryset(self):

        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return KnowledgeBase.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_create(self, serializer):

        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        if KnowledgeBase.objects.for_workspace(member.workspace_id).count() >= 20:
            raise serializers.ValidationError("A workspace can have up to 20 knowledge bases.")
        base = serializer.save(workspace=member.workspace)
        audit(member.workspace, self.request.user, "knowledge_base.created", base.id)


class KnowledgeBaseDetail(generics.RetrieveUpdateDestroyAPIView):
    """Deleting a base keeps its documents; they return to General knowledge."""

    serializer_class = KnowledgeBaseSerializer

    def get_queryset(self):

        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return KnowledgeBase.objects.for_workspace(self.kwargs["workspace_id"])


class DocumentList(generics.ListAPIView):
    serializer_class = DocumentSerializer
    parser_classes = [JSONParser, MultiPartParser]

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return KnowledgeDocument.objects.for_workspace(self.kwargs["workspace_id"]).order_by(
            "-created_at"
        )

    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        check_feature(workspace_id, "ai_agent_enabled")
        uploaded = request.FILES.get("file")
        title = str(request.data.get("title", "Knowledge document"))[:200]
        kind = "text"
        base = None
        if request.data.get("knowledge_base"):
            from .models import KnowledgeBase

            base = (
                KnowledgeBase.objects.for_workspace(workspace_id)
                .filter(pk=str(request.data["knowledge_base"])[:64])
                .first()
                if _uuid(request.data["knowledge_base"])
                else None
            )
            if base is None:
                raise serializers.ValidationError("Choose a knowledge base from this workspace.")
        url = request.data.get("url")
        if url and not uploaded:
            from .web_import import ImportError_, validate_page_url

            try:
                validate_page_url(str(url))
            except ImportError_:
                raise serializers.ValidationError("Enter a full https:// page address.") from None
            source, kind = str(url), "url"
            if title == "Knowledge document":
                title = str(url)[:200]
            uploaded = None
        if kind == "url":
            pass
        elif uploaded:
            if uploaded.size > 2 * 1024 * 1024:
                raise serializers.ValidationError("Upload a document up to 2 MB.")
            if uploaded.name.lower().endswith(".pdf"):
                source = base64.b64encode(uploaded.read()).decode()
                kind = "pdf"
            elif uploaded.name.lower().endswith(".docx"):
                source = base64.b64encode(uploaded.read()).decode()
                kind = "docx"
            elif uploaded.name.lower().endswith((".txt", ".md")):
                try:
                    source = uploaded.read().decode("utf-8")
                except UnicodeDecodeError:
                    raise serializers.ValidationError("Text documents must be UTF-8.") from None
            else:
                raise serializers.ValidationError("Upload PDF, DOCX, TXT or Markdown.")
        else:
            source = request.data.get("source", "")
            if not isinstance(source, str) or not 1 <= len(source) <= 250000:
                raise serializers.ValidationError("Provide text up to 250,000 characters.")
        document = KnowledgeDocument.objects.for_workspace(workspace_id).create(
            workspace=member.workspace,
            title=title,
            source=source,
            file_type=kind,
            knowledge_base=base,
        )
        audit(member.workspace, request.user, "knowledge.uploaded", document.id)
        return Response(DocumentSerializer(document).data, status=202)


class DocumentDetail(generics.DestroyAPIView):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return KnowledgeDocument.objects.for_workspace(self.kwargs["workspace_id"])


class AgentAuditView(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        return Response(
            {
                "runs": list(
                    AgentRun.objects.for_workspace(workspace_id)
                    .order_by("-created_at")
                    .values("id", "message_id", "status", "error_code", "created_at")[:50]
                ),
                "tools": [
                    {
                        "id": call.id,
                        "name": call.name,
                        "status": call.status,
                        "input": json.loads(call.input),
                        "output": json.loads(call.output),
                    }
                    for call in ToolCall.objects.for_workspace(workspace_id).order_by(
                        "-created_at"
                    )[:50]
                ],
                "usage": list(
                    UsageRecord.objects.for_workspace(workspace_id)
                    .order_by("-created_at")
                    .values(
                        "id",
                        "model",
                        "kind",
                        "input_tokens",
                        "output_tokens",
                        "cost",
                        "status",
                        "created_at",
                    )[:50]
                ),
            }
        )


def _uuid(value):
    import uuid

    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True
