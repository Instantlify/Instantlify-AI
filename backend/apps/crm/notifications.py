from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership

from .models import AssignmentNotification
from .services import notify


def assignment_changed(lead, recipient_id, previous_id, actor):
    if recipient_id == previous_id:
        return
    AssignmentNotification.objects.for_workspace(lead.workspace_id).filter(
        lead=lead, read_at__isnull=True
    ).update(read_at=timezone.now())
    if recipient_id and recipient_id != actor.pk:
        AssignmentNotification.objects.for_workspace(lead.workspace_id).create(
            workspace_id=lead.workspace_id, lead=lead, recipient_id=recipient_id, actor=actor
        )
    transaction.on_commit(lambda: notify(lead.workspace_id))


class AssignmentNotificationsView(APIView):
    def rows(self, request, workspace_id):
        from .views import visible_leads

        workspace_membership(request, workspace_id)
        return AssignmentNotification.objects.for_workspace(workspace_id).filter(
            recipient=request.user, lead__in=visible_leads(request, workspace_id)
        )

    def get(self, request, workspace_id):
        rows = self.rows(request, workspace_id)
        return Response(
            {
                "unread_count": rows.filter(read_at__isnull=True).count(),
                "results": [
                    {
                        "id": str(item.pk),
                        "contact_id": str(item.lead_id),
                        "contact_name": item.lead.name or item.lead.email or "Contact",
                        "assigned_by": (item.actor.get_full_name() or item.actor.email)
                        if item.actor
                        else "Your team",
                        "created_at": item.created_at,
                        "read": item.read_at is not None,
                    }
                    for item in rows.select_related("lead", "actor")[:30]
                ],
            }
        )

    def patch(self, request, workspace_id):
        rows = self.rows(request, workspace_id).filter(read_at__isnull=True)
        if request.data.get("all_read") is True:
            pass
        elif request.data.get("id"):
            pk = serializers.UUIDField().run_validation(request.data["id"])
            rows = rows.filter(pk=pk)
        else:
            raise serializers.ValidationError("Choose a notification or mark all read.")
        rows.update(read_at=timezone.now())
        transaction.on_commit(lambda: notify(workspace_id))
        return Response({"ok": True})
