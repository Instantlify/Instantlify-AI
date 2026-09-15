from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import Automation, ConversationState
from .services import publish


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
        ]
        read_only_fields = ["id", "published", "revision", "updated_at", "installed_from"]

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


class AutomationDetail(generics.RetrieveUpdateAPIView):
    serializer_class = AutomationSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return Automation.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_update(self, serializer):
        if serializer.validated_data.get("enabled") and not serializer.instance.published:
            raise serializers.ValidationError("Publish a valid flow before enabling it.")
        item = serializer.save()
        audit(item.workspace, self.request.user, "automation.updated", item.id)


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
