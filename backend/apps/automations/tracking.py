import secrets
from functools import cache

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import WorkflowLink


def validate_tracking(graph):
    nodes = {node["id"]: node["data"] for node in graph["nodes"]}
    for node_id, data in nodes.items():
        if "track_clicks" in data and not isinstance(data["track_clicks"], bool):
            raise ValidationError("Click tracking must be enabled or disabled.")
        if data.get("track_clicks") and (
            data["kind"] != "send_buttons"
            or not any(button["type"] == "web_url" for button in data.get("buttons", []))
        ):
            raise ValidationError("Track clicks on a message containing a resource link.")
        if data["kind"] == "send_reminder":
            source = data.get("source_node")
            if (
                not isinstance(source, str)
                or source not in nodes
                or not nodes[source].get("track_clicks")
            ):
                raise ValidationError("Choose a previous message with tracked resource links.")

            @cache
            def follows_source(current, source=source):
                if current == source:
                    return True
                parents = [edge["source"] for edge in graph["edges"] if edge["target"] == current]
                return bool(parents) and all(follows_source(parent) for parent in parents)

            if not follows_source(node_id):
                raise ValidationError(
                    "Every path to the reminder must send the tracked resource first."
                )


def tracked_buttons(state, buttons):
    result = []
    for index, button in enumerate(buttons):
        if button["type"] != "web_url":
            result.append(button)
            continue
        link, _ = WorkflowLink.objects.for_workspace(state.workspace_id).get_or_create(
            key=f"{state.run_token}:{state.node_id}:{state.steps}:{index}",
            defaults={
                "workspace_id": state.workspace_id,
                "state": state,
                "conversation": state.conversation,
                "run_token": state.run_token,
                "source_node": state.node_id,
                "code": secrets.token_urlsafe(24),
                "target": button["url"],
                "automation_id": state.automation_id,
                "experiment_id": state.experiment_id,
                "variant": state.variant,
            },
        )
        result.append({**button, "url": f"{settings.PUBLIC_APP_URL.rstrip('/')}/r/{link.code}/"})
    return result


def clicked(workspace_id, condition):
    return (
        WorkflowLink.objects.for_workspace(workspace_id)
        .filter(
            run_token=condition["run_token"],
            source_node=condition["source_node"],
            conversation_id=condition["conversation_id"],
            clicked_at__isnull=False,
        )
        .exists()
    )


class WorkflowLinkRedirect(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def get(self, request, code):
        with transaction.atomic():
            link = get_object_or_404(
                WorkflowLink.all_objects.select_for_update().select_related(
                    "conversation__identity__lead", "conversation__identity__connection"
                ),
                code=code,
            )
            if (
                request.method != "HEAD"
                and not link.clicked_at
                and not link.conversation.identity.lead.opted_out
            ):
                link.clicked_at = timezone.now()
                link.save(update_fields=["clicked_at"])
                from apps.analytics.services import record

                record(
                    link.workspace_id,
                    "link_click",
                    key=f"workflow_link:{link.pk}",
                    provider=link.conversation.identity.connection.provider,
                    lead_id=link.conversation.identity.lead_id,
                    conversation_id=link.conversation_id,
                    automation_id=link.automation_id,
                    experiment_id=link.experiment_id,
                    variant=link.variant,
                )
        response = HttpResponseRedirect(link.target)
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response
