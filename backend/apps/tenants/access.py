"""Per-member access limits: which workspace sections and which channel accounts a
teammate may use. Empty lists mean no limit (the default). Owners are never limited.

Sections are enforced centrally from the request path (see `section_allowed`), so a
hidden section's API is refused, not just its menu item. Shared lookups the inbox and
CRM depend on (connections list, stages, fields, members, status) stay open.
"""

import re

SECTIONS = {
    "inbox": "Inbox",
    "crm": "CRM",
    "automations": "Automations",
    "agent": "AI agent",
    "analytics": "Analytics",
    "integrations": "Integrations",
    "payments": "Payments",
    "bio": "Link in bio",
    "forms": "Forms",
    "calendar": "Content calendar",
    "shield": "Comment shield",
    "deeplinks": "Tracking links",
    "webchat": "Web chat",
    "creator-kit": "Creator kit",
}

# First path segment after /api/workspaces/<id>/ -> sections that grant it.
PATH_SECTIONS = {
    "conversations": {"inbox", "crm"},
    "saved-replies": {"inbox"},
    "assignment-notifications": {"inbox", "crm"},
    "leads": {"inbox", "crm"},
    "segments": {"crm"},
    "campaigns": {"crm"},
    "automations": {"automations"},
    "automation-runs": {"automations"},
    "templates": {"automations"},
    "experiments": {"automations", "analytics"},
    "agent": {"agent"},
    "agent-audit": {"agent"},
    "documents": {"agent"},
    "knowledge-bases": {"agent", "automations"},
    "analytics": {"analytics"},
    "integrations": {"integrations", "automations"},
    "channels": {"integrations"},
    "telegram": {"integrations"},
    "whatsapp": {"integrations"},
    "meta": {"integrations"},
    "linkedin": {"integrations"},
    "api-keys": {"integrations"},
    "webhooks": {"integrations"},
    "webhook-deliveries": {"integrations"},
    "deliveries": {"integrations"},
    "offers": {"inbox", "payments"},
    "payments": {"payments"},
    "bio": {"bio"},
    "forms": {"forms"},
    "posts": {"calendar"},
    "shield": {"shield"},
    "deeplinks": {"deeplinks"},
    "webchat": {"webchat"},
    "creator-kit": {"creator-kit"},
}
WORKSPACE_PATH = re.compile(r"^/api/workspaces/[0-9a-fA-F-]{36}/([a-z-]+)/")


def section_allowed(membership, path):
    allowed = membership.allowed_sections or []
    if membership.role == "owner" or not allowed:
        return True
    match = WORKSPACE_PATH.match(path or "")
    needed = PATH_SECTIONS.get(match.group(1)) if match else None
    return needed is None or bool(needed & set(allowed))


def connection_ids(membership):
    """Channel accounts this member may see, or None for all."""
    if membership.role == "owner" or not membership.allowed_connections:
        return None
    return [str(item) for item in membership.allowed_connections]


def validate_access(workspace_id, sections, connections):
    from rest_framework import serializers

    from apps.channels.models import ChannelConnection

    if not isinstance(sections, list) or any(item not in SECTIONS for item in sections):
        raise serializers.ValidationError({"allowed_sections": "Choose known sections."})
    if not isinstance(connections, list) or len(connections) > 100:
        raise serializers.ValidationError({"allowed_connections": "Choose channel accounts."})
    known = {
        str(pk)
        for pk in ChannelConnection.objects.for_workspace(workspace_id).values_list("pk", flat=True)
    }
    if any(str(item) not in known for item in connections):
        raise serializers.ValidationError(
            {"allowed_connections": "Choose accounts connected to this workspace."}
        )
    return list(dict.fromkeys(sections)), list(dict.fromkeys(str(c) for c in connections))
