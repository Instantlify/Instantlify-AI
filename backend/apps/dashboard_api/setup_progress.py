"""Which setup steps a workspace has actually completed, derived from its data."""

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership


def progress(workspace_id):
    from apps.agents.models import AgentConfig, KnowledgeDocument
    from apps.automations.models import Automation
    from apps.channels.models import ChannelConnection
    from apps.content.models import BioPage
    from apps.tenants.models import Membership
    from apps.tools.models import LeadForm, WebChatSettings

    return [
        {
            "id": "connect_channel",
            "done": ChannelConnection.objects.for_workspace(workspace_id)
            .filter(status="active")
            .exists(),
        },
        {
            "id": "publish_automation",
            "done": Automation.objects.for_workspace(workspace_id)
            .filter(enabled=True)
            .exclude(published={})
            .exists(),
        },
        {
            "id": "configure_agent",
            "done": AgentConfig.objects.for_workspace(workspace_id).filter(enabled=True).exists(),
        },
        {
            "id": "add_knowledge",
            "done": KnowledgeDocument.objects.for_workspace(workspace_id)
            .filter(status="ready")
            .exists(),
        },
        {
            "id": "publish_bio",
            "done": BioPage.objects.for_workspace(workspace_id).filter(published=True).exists(),
        },
        {"id": "create_form", "done": LeadForm.objects.for_workspace(workspace_id).exists()},
        {
            "id": "setup_webchat",
            "done": WebChatSettings.objects.for_workspace(workspace_id).exists(),
        },
        {
            "id": "invite_team",
            "done": Membership.objects.for_workspace(workspace_id).count() > 1,
        },
    ]


class SetupProgressView(APIView):
    def get(self, request, workspace_id):
        member = workspace_membership(request, workspace_id)
        steps = progress(member.workspace_id)
        return Response({"steps": steps, "completed": sum(step["done"] for step in steps)})
