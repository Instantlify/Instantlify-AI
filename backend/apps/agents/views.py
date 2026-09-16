import base64
import json

from django.conf import settings
from rest_framework import generics, serializers
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import AgentConfig, AgentRun, KnowledgeDocument, ToolCall, UsageRecord
from .tools import SCHEMAS


class AgentSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_key = serializers.SerializerMethodField()

    def get_has_key(self, obj):
        return bool(obj.api_key)

    def validate(self, attrs):
        if attrs.get("provider", "openai") != "openai":
            raise serializers.ValidationError(
                "This release supports OpenAI and the local test provider."
            )
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
            "allowed_tools",
            "enabled",
            "is_test",
            "input_cost_per_million",
            "output_cost_per_million",
            "qualifying_fields",
            "triage_enabled",
            "handoff_keywords",
            "max_tool_rounds",
        ]
        read_only_fields = ["id", "has_key"]


class AgentView(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        config = AgentConfig.objects.for_workspace(workspace_id).first()
        return Response(AgentSerializer(config).data if config else {})

    def put(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        config = AgentConfig.objects.for_workspace(workspace_id).first()
        serializer = AgentSerializer(config, data=request.data, partial=bool(config))
        serializer.is_valid(raise_exception=True)
        config = serializer.save(workspace=member.workspace)
        audit(member.workspace, request.user, "agent.configured", config.id)
        return Response(serializer.data)


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeDocument
        fields = ["id", "title", "status", "error_code", "embedding_model", "created_at"]


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
        uploaded = request.FILES.get("file")
        title = str(request.data.get("title", "Knowledge document"))[:200]
        kind = "text"
        if uploaded:
            if uploaded.size > 2 * 1024 * 1024:
                raise serializers.ValidationError("Upload a document up to 2 MB.")
            if uploaded.name.lower().endswith(".pdf"):
                source = base64.b64encode(uploaded.read()).decode()
                kind = "pdf"
            elif uploaded.name.lower().endswith((".txt", ".md")):
                try:
                    source = uploaded.read().decode("utf-8")
                except UnicodeDecodeError:
                    raise serializers.ValidationError("Text documents must be UTF-8.") from None
            else:
                raise serializers.ValidationError("Upload PDF, TXT or Markdown.")
        else:
            source = request.data.get("source", "")
            if not isinstance(source, str) or not 1 <= len(source) <= 250000:
                raise serializers.ValidationError("Provide text up to 250,000 characters.")
        document = KnowledgeDocument.objects.for_workspace(workspace_id).create(
            workspace=member.workspace, title=title, source=source, file_type=kind
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
