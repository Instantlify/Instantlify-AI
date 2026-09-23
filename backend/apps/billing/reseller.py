"""Reseller (Agency) consolidated billing services.

When an agency manages client workspaces (`workspace.parent` is set):
- Subscription status, plan tier and limits roll up to the parent agency.
- Prepaid AI credits and usage ledger debit the parent agency's balance.
- Child workspaces do not require separate Stripe customers or subscriptions.
"""

from uuid import UUID

from apps.tenants.models import Workspace

from .models import BillingAccount


def effective_billing_workspace_id(workspace_id: UUID | str) -> UUID | str:
    """Returns the ID of the workspace responsible for billing.

    If the workspace is a child workspace managed by an agency (`parent` is set),
    billing rolls up to the parent agency workspace.
    """
    if not workspace_id:
        return workspace_id
    workspace = Workspace.objects.filter(pk=workspace_id).values("id", "parent_id").first()
    if workspace and workspace.get("parent_id"):
        return workspace["parent_id"]
    return workspace_id


def is_reseller_client(workspace_id: UUID | str) -> bool:
    """Returns True if the workspace is managed under a parent agency."""
    if not workspace_id:
        return False
    return Workspace.objects.filter(pk=workspace_id, parent__isnull=False).exists()


def get_parent_agency(workspace_id: UUID | str) -> Workspace | None:
    """Returns the parent agency Workspace instance if this is a managed client workspace."""
    workspace = Workspace.objects.filter(pk=workspace_id).select_related("parent").first()
    return workspace.parent if workspace else None


def effective_billing_account(workspace_id: UUID | str) -> BillingAccount:
    """Returns the BillingAccount responsible for this workspace (agency or self)."""
    target_id = effective_billing_workspace_id(workspace_id)
    return BillingAccount.objects.for_workspace(target_id).get_or_create(workspace_id=target_id)[0]
