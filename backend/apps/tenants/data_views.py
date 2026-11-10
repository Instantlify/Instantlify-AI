import json

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DataOperation
from .permissions import workspace_membership
from .services import audit


class DataOperationsView(APIView):
    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner"])
        return Response(
            list(
                DataOperation.objects.for_workspace(workspace_id)
                .order_by("-created_at")
                .values("id", "kind", "status", "error_code", "created_at")[:20]
            )
        )

    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner"])
        kind = request.data.get("kind")
        if kind not in {"export", "delete"}:
            raise ValidationError("Choose export or delete.")
        if not request.user.check_password(str(request.data.get("password", ""))):
            raise ValidationError("Confirm your password.")
        if kind == "delete" and request.data.get("confirmation") != member.workspace.name:
            raise ValidationError("Enter the exact workspace name to confirm deletion.")
        job = (
            DataOperation.objects.for_workspace(workspace_id)
            .filter(kind=kind, status="pending")
            .first()
        )
        if not job:
            job = DataOperation.objects.for_workspace(workspace_id).create(
                workspace=member.workspace, kind=kind
            )
        audit(member.workspace, request.user, "data." + kind + "_requested", job.id)
        return Response({"id": job.id, "status": job.status}, status=202)


class DownloadExportView(APIView):
    def get(self, request, workspace_id, pk):
        from django.shortcuts import get_object_or_404

        workspace_membership(request, workspace_id, ["owner"])
        job = get_object_or_404(
            DataOperation.objects.for_workspace(workspace_id),
            pk=pk,
            kind="export",
            status="complete",
        )
        response = Response(json.loads(job.result))
        response["Content-Disposition"] = 'attachment; filename="instantlify-export.json"'
        response["Cache-Control"] = "private, no-store"
        return response
