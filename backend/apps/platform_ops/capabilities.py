"""Workspace approvals, independent of plans and provider OAuth permissions."""

from rest_framework.exceptions import PermissionDenied

from .models import WorkspaceCapability

CAPABILITIES = {
    "meta_analytics": "Meta analytics and live statistics",
    "meta_publishing": "Meta content publishing",
}


def capabilities_for(workspace_id):
    granted = set(
        WorkspaceCapability.objects.filter(workspace_id=workspace_id, enabled=True).values_list(
            "key", flat=True
        )
    )
    return {key: key in granted for key in CAPABILITIES}


def has_capability(workspace_id, key):
    if key not in CAPABILITIES:
        raise ValueError(f"Unknown workspace capability: {key}")
    return WorkspaceCapability.objects.filter(
        workspace_id=workspace_id, key=key, enabled=True
    ).exists()


def check_capability(workspace_id, key):
    if not has_capability(workspace_id, key):
        raise PermissionDenied(
            {
                "detail": "This feature requires approval from the platform administrator.",
                "code": "capability_approval_required",
                "capability": key,
            }
        )
