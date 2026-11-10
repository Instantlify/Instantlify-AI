"""Workspace pipeline stages: ordered, renamable, colourable CRM stages.

Four stages are system stages because the platform moves contacts into them on its own
(new contacts, bookings, payments, losses): they can be renamed and recoloured but never
removed. Workspaces add up to 20 stages in total. Removing a custom stage moves its
contacts back to "new" so no contact is left in a stage that no longer exists.
"""

import re

from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

DEFAULT_STAGES = [
    {"id": "new", "label": "No stage", "color": "#94a3b8"},
    {"id": "qualified", "label": "Qualified", "color": "#6366f1"},
    {"id": "interested", "label": "Interested", "color": "#f59e0b"},
    {"id": "booked", "label": "Booked", "color": "#0ea5e9"},
    {"id": "won", "label": "Won", "color": "#16a34a"},
    {"id": "lost", "label": "Lost", "color": "#ef4444"},
]
SYSTEM = {"new", "booked", "won", "lost"}
STAGE_ID = re.compile(r"[a-z][a-z0-9_]{0,19}")
COLOR = re.compile(r"#[0-9a-fA-F]{6}")
MAX_STAGES = 20


def stages_for(workspace_id):
    from apps.tenants.models import Workspace

    saved = (
        Workspace.objects.filter(pk=workspace_id).values_list("pipeline_stages", flat=True).first()
    )
    return saved or [dict(stage) for stage in DEFAULT_STAGES]


def stage_ids(workspace_id):
    return {stage["id"] for stage in stages_for(workspace_id)}


def validate_stage_for(workspace_id, value):
    if not isinstance(value, str) or value not in stage_ids(workspace_id):
        raise serializers.ValidationError("Invalid stage.")
    return value


def validate_stages(value):
    if not isinstance(value, list) or not len(SYSTEM) <= len(value) <= MAX_STAGES:
        raise serializers.ValidationError(f"Keep between {len(SYSTEM)} and {MAX_STAGES} stages.")
    cleaned, seen = [], set()
    for stage in value:
        if not isinstance(stage, dict):
            raise serializers.ValidationError("Each stage needs an id, label and colour.")
        stage_id = stage.get("id")
        label = stage.get("label")
        color = stage.get("color", "#94a3b8")
        if not isinstance(stage_id, str) or not STAGE_ID.fullmatch(stage_id):
            raise serializers.ValidationError(
                "Stage ids use lowercase letters, digits and _ (up to 20 characters)."
            )
        if stage_id in seen:
            raise serializers.ValidationError("Stage ids must be unique.")
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 40:
            raise serializers.ValidationError("Each stage needs a name of 1–40 characters.")
        if not isinstance(color, str) or not COLOR.fullmatch(color):
            raise serializers.ValidationError("Colours must look like #22c55e.")
        seen.add(stage_id)
        cleaned.append({"id": stage_id, "label": label.strip(), "color": color.lower()})
    if not SYSTEM <= seen:
        raise serializers.ValidationError("No stage, Booked, Won and Lost cannot be removed.")
    return cleaned


class PipelineStagesView(APIView):
    def get(self, request, workspace_id):
        member = workspace_membership(request, workspace_id)
        return Response({"stages": stages_for(member.workspace_id), "system": sorted(SYSTEM)})

    def put(self, request, workspace_id):
        from apps.tenants.models import Workspace

        from .models import Lead

        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        stages = validate_stages(request.data.get("stages"))
        kept = {stage["id"] for stage in stages}
        with transaction.atomic():
            workspace = Workspace.objects.select_for_update().get(pk=member.workspace_id)
            removed = stage_ids(workspace.pk) - kept
            moved = (
                Lead.objects.for_workspace(workspace).filter(stage__in=removed).update(stage="new")
                if removed
                else 0
            )
            workspace.pipeline_stages = stages
            workspace.save(update_fields=["pipeline_stages"])
            audit(workspace, request.user, "pipeline.stages_updated", workspace.pk)
        return Response({"stages": stages, "system": sorted(SYSTEM), "moved_contacts": moved})
