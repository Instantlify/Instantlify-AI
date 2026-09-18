"""Tenant isolation below `save()`: bulk writes, queryset updates and raw SQL.

The PostgreSQL tests need a PostgreSQL test database (the default suite runs on SQLite
and skips them). Run them with, for example:

    DATABASE_URL=postgres://postgres:postgres@127.0.0.1:55432/nemio \\
        uv run pytest tests/test_tenant_db_isolation.py
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.automations.models import Automation, Edge, Node, Trigger
from apps.channels.models import ChannelConnection
from apps.crm.models import ChannelIdentity, Conversation, Lead
from apps.tenants.isolation import installed, tenant_links, trigger_sql
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db
postgres_only = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="database triggers are PostgreSQL-only"
)


@pytest.fixture
def other(user):
    return create_workspace(user, "Other tenant")


def lead_in(workspace, name="Lead"):
    return Lead.objects.for_workspace(workspace).create(workspace=workspace, name=name)


def channel_in(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id=f"acct-{workspace.pk}",
        display_name="x",
        access_token="t",
        expires_at=timezone.now() + timedelta(days=1),
        is_test=True,
    )


def identities(workspace, lead, channel):
    return ChannelIdentity(
        workspace=workspace, lead=lead, connection=channel, external_id=f"ext-{lead.pk}"
    )


# --- Python layer (every database)


def test_bulk_create_rejects_cross_tenant_links(workspace, other):
    foreign_lead = lead_in(other)
    channel = channel_in(workspace)
    with pytest.raises(ValidationError):
        ChannelIdentity.objects.for_workspace(workspace).bulk_create(
            [identities(workspace, foreign_lead, channel)]
        )
    with pytest.raises(ValidationError):  # the unscoped manager is guarded too
        ChannelIdentity.all_objects.bulk_create([identities(workspace, foreign_lead, channel)])
    own = ChannelIdentity.all_objects.bulk_create(
        [identities(workspace, lead_in(workspace), channel)]
    )
    assert len(own) == 1


def test_bulk_update_rejects_repointing_to_another_tenant(workspace, other):
    identity = ChannelIdentity.objects.for_workspace(workspace).create(
        workspace=workspace,
        lead=lead_in(workspace),
        connection=channel_in(workspace),
        external_id="e",
    )
    identity.lead = lead_in(other)
    with pytest.raises(ValidationError):
        ChannelIdentity.all_objects.bulk_update([identity], ["lead"])
    identity.lead = lead_in(workspace, "Second")
    ChannelIdentity.all_objects.bulk_update([identity], ["lead"])  # same tenant is fine


def test_every_tenant_link_is_covered():
    links = tenant_links()
    assert ("crm_message", "conversation_id", "crm_conversation") in links
    assert ("automations_edge", "automation_id", "automations_automation") in links
    assert not any(column == "workspace_id" for _, column, _ in links)
    statements, names = trigger_sql(links)
    children = {child for child, _, _ in links}
    parents = {parent for _, _, parent in links}
    assert {table for table, _ in names} == children | parents


# --- Database layer (PostgreSQL)


def check_now():
    """Deferred triggers fire at commit, which a test transaction never reaches; this
    runs every pending check immediately, raising on a violation."""
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


@postgres_only
def test_triggers_are_installed_for_every_link():
    expected = {table for table, _ in trigger_sql(tenant_links())[1]}
    assert expected <= {table for table, _ in installed()}


@postgres_only
def test_queryset_update_cannot_cross_tenants(workspace, other):
    lead = lead_in(workspace)
    identity = ChannelIdentity.objects.for_workspace(workspace).create(
        workspace=workspace, lead=lead, connection=channel_in(workspace), external_id="e"
    )
    conversation = Conversation.objects.for_workspace(workspace).create(
        workspace=workspace, identity=identity
    )
    foreign = ChannelIdentity.objects.for_workspace(other).create(
        workspace=other, lead=lead_in(other), connection=channel_in(other), external_id="f"
    )
    with pytest.raises(IntegrityError, match="cross_tenant_fk_violation"), transaction.atomic():
        # update() never calls save(): only the database can refuse this.
        Conversation.all_objects.filter(pk=conversation.pk).update(identity_id=foreign.pk)
        check_now()
    with pytest.raises(IntegrityError, match="cross_tenant_fk_violation"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE crm_conversation SET identity_id = %s WHERE id = %s",
                [foreign.pk, conversation.pk],
            )
        check_now()


@postgres_only
def test_parent_cannot_move_without_its_children(workspace, other):
    automation = Automation.objects.for_workspace(workspace).create(workspace=workspace, name="a")
    Node.objects.for_workspace(workspace).create(
        workspace=workspace, automation=automation, node_id="n", kind="end", config={}
    )
    with pytest.raises(IntegrityError, match="left in another workspace"), transaction.atomic():
        Automation.all_objects.filter(pk=automation.pk).update(workspace=other)
        check_now()


@postgres_only
def test_consistent_transfer_passes_at_commit(workspace, other, user):
    from apps.automations.services import transfer

    automation = Automation.objects.for_workspace(workspace).create(workspace=workspace, name="a")
    for model, values in [
        (Node, {"node_id": "n", "kind": "end", "config": {}}),
        (Trigger, {"kind": "dm", "keyword": "hi"}),
        (Edge, {"source": "n", "target": "m"}),
    ]:
        model.objects.for_workspace(workspace).create(
            workspace=workspace, automation=automation, **values
        )
    # Children are re-homed before their parent: only valid once all rows have moved.
    transfer(automation, other, operator=user, reason="support ticket 12")
    check_now()
    assert Node.all_objects.get(automation=automation).workspace_id == other.pk


@postgres_only
def test_rows_deleted_before_commit_are_not_false_violations(workspace):
    lead = lead_in(workspace)
    ChannelIdentity.objects.for_workspace(workspace).create(
        workspace=workspace, lead=lead, connection=channel_in(workspace), external_id="e"
    )
    workspace.delete()  # cascades after the identity's check was queued
    check_now()
