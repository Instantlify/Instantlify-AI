from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.automations.models import Automation
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import Experiment
from .services import experiment_results, funnel, promote


class FunnelView(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        automation_id = request.query_params.get("automation") or None
        if automation_id:
            get_object_or_404(Automation.objects.for_workspace(workspace_id), pk=automation_id)
        return Response(
            funnel(
                workspace_id,
                period=request.query_params.get("period", "30d"),
                automation_id=automation_id,
                provider=request.query_params.get("provider", "")[:30],
            )
        )


class ExperimentSerializer(serializers.ModelSerializer):
    results = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The default manager fails closed; scope FK choices to the caller's tenant.
        scoped = Automation.objects.for_workspace(self.context["workspace_id"])
        self.fields["control"].queryset = scoped
        self.fields["variant"].queryset = scoped

    def get_results(self, obj):
        return experiment_results(obj)

    def validate(self, attrs):
        workspace_id = self.context["workspace_id"]
        for field in ["control", "variant"]:
            automation = attrs.get(field)
            if automation and automation.workspace_id != workspace_id:
                raise serializers.ValidationError("Choose automations from this workspace.")
        if attrs.get("control") and attrs.get("control") == attrs.get("variant"):
            raise serializers.ValidationError("Control and variant must differ.")
        if attrs.get("goal", "booked") not in {"replied", "booked", "paid"}:
            raise serializers.ValidationError("Goal must be replied, booked or paid.")
        return attrs

    class Meta:
        model = Experiment
        fields = [
            "id",
            "name",
            "control",
            "variant",
            "split",
            "goal",
            "status",
            "winner",
            "auto_promote",
            "min_leads",
            "concluded_at",
            "results",
            "created_at",
        ]
        read_only_fields = ["id", "status", "winner", "concluded_at", "results", "created_at"]
        extra_kwargs = {"split": {"min_value": 1, "max_value": 99}}


class ExperimentList(generics.ListCreateAPIView):
    serializer_class = ExperimentSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "workspace_id": self.kwargs["workspace_id"]}

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return Experiment.objects.for_workspace(self.kwargs["workspace_id"]).order_by("-created_at")

    def perform_create(self, serializer):
        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        if (
            Experiment.objects.for_workspace(member.workspace_id)
            .filter(control=serializer.validated_data["control"], status="running")
            .exists()
        ):
            raise serializers.ValidationError("That automation already has a running experiment.")
        item = serializer.save(workspace=member.workspace)
        audit(member.workspace, self.request.user, "experiment.created", item.id)


class ExperimentDetail(APIView):
    def post(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        experiment = get_object_or_404(Experiment.objects.for_workspace(workspace_id), pk=pk)
        winner = request.data.get("winner")
        if winner not in {"control", "variant"}:
            raise serializers.ValidationError("Choose control or variant as the winner.")
        experiment = promote(experiment, winner, request.user)
        return Response(
            ExperimentSerializer(experiment, context={"workspace_id": member.workspace_id}).data
        )
