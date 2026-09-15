from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import OutboxEvent
from apps.tenants.permissions import workspace_membership


def live(request):
    return JsonResponse({"status": "ok"})


def dependency_status():
    checks = {"database": False, "redis": False, "worker": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = cursor.fetchone()[0] == 1
    except Exception:
        pass
    try:
        cache.set("health:probe", "ok", timeout=10)
        checks["redis"] = cache.get("health:probe") == "ok"
        checks["worker"] = cache.get("worker:last_heartbeat") is not None
    except Exception:
        pass
    return checks


def ready(request):
    checks = dependency_status()
    return JsonResponse(
        {"status": "ok" if all(checks.values()) else "degraded", "checks": checks},
        status=200 if all(checks.values()) else 503,
    )


class WorkspaceStatusView(APIView):
    def get(self, request, workspace_id):
        member = workspace_membership(request, workspace_id)
        return Response(
            {
                "checks": dependency_status(),
                "pending_jobs": OutboxEvent.objects.for_workspace(member.workspace)
                .filter(processed_at__isnull=True)
                .count(),
            }
        )
