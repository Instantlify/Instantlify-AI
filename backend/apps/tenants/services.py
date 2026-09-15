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
    return workspace
