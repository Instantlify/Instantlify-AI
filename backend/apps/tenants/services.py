from django.conf import settings
from django.db import transaction

from .models import AuditEvent, Membership, OutboxEvent, Workspace


def audit(workspace, actor, action, target_id="", **metadata):
    allowed = {key: value for key, value in metadata.items() if key in {"role", "provider"}}
    return AuditEvent.objects.for_workspace(workspace).create(
        workspace=workspace, actor=actor, action=action, target_id=str(target_id), metadata=allowed
    )


@transaction.atomic
def create_workspace(user, name):
    workspace = Workspace.objects.create(name=name)
    Membership.objects.for_workspace(workspace).create(
        workspace=workspace, user=user, role=Membership.Role.OWNER
    )
    audit(workspace, user, "workspace.created", workspace.id)
    # Durable outbox closes the DB-commit / broker-publish crash window. Beat
    # retries pending IDs; tasks are idempotent and carry no secrets or payloads.
    OutboxEvent.objects.for_workspace(workspace).create(
        workspace=workspace, kind="workspace.created"
    )
    announce_workspace(workspace, user)
    return workspace


def announce_workspace(workspace, user):
    """Welcome email and the wizard's `workspace` step. Both are reporting, not the
    transaction: a bounced email or a full funnel table must never lose a workspace."""
    from apps.platform_ops import growth

    try:
        growth.record_funnel_event(
            flow="wizard", step="workspace", status="completed", user=user, workspace=workspace
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        growth.send_transactional_email(
            "welcome-v2",
            user.email,
            {
                "name": user.first_name or "there",
                "workspace": workspace.name,
                "app_url": f"{settings.PUBLIC_APP_URL}/w/{workspace.pk}/overview",
            },
        )
    except Exception:  # noqa: BLE001
        pass
