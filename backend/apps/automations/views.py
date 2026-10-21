import uuid

from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import Automation, ConversationState
from .services import in_experiment, publish, transfer


class AutomationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Automation
        fields = [
            "id",
            "name",
            "draft",
            "published",
            "revision",
            "enabled",
            "updated_at",
            "installed_from",
            "folder",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "published",
            "revision",
            "updated_at",
            "installed_from",
            "created_at",
        ]

    def validate_folder(self, value):
        return value.strip()

    def validate_draft(self, value):
        import json

        if not isinstance(value, dict) or len(json.dumps(value)) > 100000:
            raise serializers.ValidationError("Invalid or oversized draft.")
        return value


class AutomationList(generics.ListCreateAPIView):
    serializer_class = AutomationSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return Automation.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_create(self, serializer):
        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        item = serializer.save(workspace=member.workspace, enabled=False)
        audit(member.workspace, self.request.user, "automation.created", item.id)


class AutomationDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AutomationSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return Automation.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_update(self, serializer):
        if serializer.validated_data.get("enabled") and not serializer.instance.published:
            raise serializers.ValidationError("Publish a valid flow before enabling it.")
        item = serializer.save()
        audit(item.workspace, self.request.user, "automation.updated", item.id)

    def perform_destroy(self, instance):
        # Experiments cascade with their arms; refuse rather than erase their results.
        if in_experiment(instance):
            raise serializers.ValidationError(
                "Delete the A/B experiment that uses this automation first."
            )
        audit(instance.workspace, self.request.user, "automation.deleted", instance.id)
        instance.delete()


class DuplicateView(APIView):
    def post(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        item = get_object_or_404(Automation.objects.for_workspace(workspace_id), pk=pk)
        # The working draft is copied as-is (it may still be unfinished); the copy is a
        # disabled draft that never fires until someone publishes it.
        copy = Automation.objects.for_workspace(workspace_id).create(
            workspace=member.workspace,
            name=f"{item.name[:93]} (copy)",
            draft=item.draft or item.published,
            folder=item.folder,
            enabled=False,
        )
        audit(member.workspace, request.user, "automation.duplicated", copy.id)
        return Response(AutomationSerializer(copy).data, status=201)


class TransferView(APIView):
    def post(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        item = get_object_or_404(Automation.objects.for_workspace(workspace_id), pk=pk)
        try:
            target_id = uuid.UUID(str(request.data.get("workspace", "")))
        except ValueError:
            raise serializers.ValidationError("Choose a destination workspace.") from None
        target = workspace_membership(request, target_id, ["owner", "admin"]).workspace
        try:
            transfer(item, target, operator=request.user, reason=request.data.get("reason", ""))
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from None
        audit(target, request.user, "automation.transferred", item.id)
        return Response({"id": item.id, "workspace": target.id})


class StatsView(APIView):
    """All-time trigger counts per automation: runs, and distinct leads reached."""

    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        from django.db.models import Count

        from apps.analytics.models import FunnelEvent

        rows = (
            FunnelEvent.objects.for_workspace(workspace_id)
            .filter(kind="triggered")
            .exclude(automation_id=None)
            .values("automation_id")
            .annotate(runs=Count("id"), reach=Count("lead_id", distinct=True))
        )
        return Response(
            {
                str(row["automation_id"]): {"runs": row["runs"], "reach": row["reach"]}
                for row in rows
            }
        )


class GenerateInput(serializers.Serializer):
    prompt = serializers.CharField(max_length=1000)


class GenerateView(APIView):
    """Draft a flow from a plain-language request with the workspace's AI model. The
    result is validated like any flow and saved as a disabled draft for review."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request, workspace_id):
        from apps.agents.models import AgentConfig
        from apps.agents.providers import provider_for
        from apps.billing.gating import check_feature
        from apps.billing.services import complete_usage, reserve_usage
        from apps.channels.transport import ProviderError

        from .generator import SYSTEM_PROMPT, graph_from_completion

        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        check_feature(workspace_id, "ai_agent_enabled")
        body = GenerateInput(data=request.data)
        body.is_valid(raise_exception=True)
        config = AgentConfig.objects.for_workspace(workspace_id).first()
        if not config:
            return Response(
                {"detail": "Save your AI assistant settings before generating flows."},
                status=400,
            )
        usage = reserve_usage(config, f"flow-generation:{uuid.uuid4()}", kind="flow_generation")
        try:
            completion = provider_for(config).complete(
                [
                    {"role": "developer", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": body.validated_data["prompt"]},
                ],
                [],
            )
        except ProviderError:
            usage.status = "failed"
            usage.save(update_fields=["status"])
            return Response(
                {"detail": "The AI model could not draft a flow right now. Try again shortly."},
                status=503,
            )
        complete_usage(usage, completion, config)
        name, graph = graph_from_completion(completion.text)
        item = Automation.objects.for_workspace(workspace_id).create(
            workspace=member.workspace, name=name, draft=graph, enabled=False
        )
        audit(member.workspace, request.user, "automation.generated", item.id)
        return Response(AutomationSerializer(item).data, status=201)


class PublishView(APIView):
    def post(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        item = get_object_or_404(Automation.objects.for_workspace(workspace_id), pk=pk)
        result = publish(item, request.data.get("graph", item.draft), request.user)
        return Response(AutomationSerializer(result).data)


class ExportView(APIView):
    def get(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        item = get_object_or_404(Automation.objects.for_workspace(workspace_id), pk=pk)
        from .templates import export_automation

        response = Response(export_automation(item))
        response["Content-Disposition"] = 'attachment; filename="automation.json"'
        return response


class ImportView(APIView):
    parser_classes = [JSONParser, MultiPartParser]

    def post(self, request, workspace_id):
        from .templates import import_automation

        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        uploaded = request.FILES.get("file")
        if uploaded:
            if uploaded.size > 200_000:
                raise serializers.ValidationError("Template files must be under 200 KB.")
            document = uploaded.read()
        else:
            document = request.data.get("template")
        item = import_automation(member.workspace, document, request.user)
        return Response(AutomationSerializer(item).data, status=201)


class RunsView(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        return Response(
            list(
                ConversationState.objects.for_workspace(workspace_id)
                .order_by("-created_at")
                .values(
                    "id",
                    "automation_id",
                    "conversation_id",
                    "status",
                    "steps",
                    "node_id",
                    "error_code",
                )[:100]
            )
        )
