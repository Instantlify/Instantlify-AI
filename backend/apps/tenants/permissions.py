from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from .models import Membership

READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def workspace_membership(
    request, workspace_id, roles=None, *, allow_pending=False, allow_viewer_write=False
):
    # A nonexistent workspace and another tenant's workspace have the same response.
    membership = get_object_or_404(
        Membership.objects.for_workspace(workspace_id).select_related("workspace"),
        user=request.user,
    )
    if roles is not None and membership.role not in roles:
        raise PermissionDenied("Your role cannot perform this action.")
    # Viewers see what members see but change nothing, enforced here for every endpoint.
    if (
        membership.role == "viewer"
        and request.method not in READ_METHODS
        and not allow_viewer_write
    ):
        raise PermissionDenied("Viewers have read-only access.")
    from .access import section_allowed

    if not section_allowed(membership, request.path):
        raise PermissionDenied("You do not have access to this part of the workspace.")
    from apps.platform_ops.security import blocked

    if blocked(workspace_id):
        raise PermissionDenied("This workspace is suspended. Contact support.")
    if membership.workspace.checkout_pending and not allow_pending:
        raise PermissionDenied("Complete checkout to open this workspace.", code="checkout_pending")
    return membership
