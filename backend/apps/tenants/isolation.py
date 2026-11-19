"""Tenant isolation enforced by the database, not only by `TenantModel.save()`.

Every foreign key from one tenant table to another must point at a row in the same
workspace. `save()` checks that in Python, but `bulk_create`, `bulk_update`,
`QuerySet.update()` and raw SQL never call `save()`. On PostgreSQL this module installs
constraint triggers that hold the invariant for every write path:

* child side: an inserted/updated row's tenant FKs must reference rows in its workspace;
* parent side: a row whose `workspace_id` changes must not leave children behind.

Triggers are DEFERRABLE INITIALLY DEFERRED so a multi-row move that is consistent at
commit (automations.services.transfer re-homes children before their parent) passes,
and each check re-reads the current row, so a row inserted and then deleted in the same
transaction is not a false violation.

Installed by a post_migrate hook and generated from model metadata, so a tenant table
added later is covered the next time migrations run. SQLite (the unit-test database)
relies on `TenantModel.save()` and `TenantQuerySet`'s bulk checks instead.
"""

from collections import defaultdict

PREFIX = "instantlify_tenant"


def tenant_links():
    """[(child_table, column, parent_table)] for every FK between two tenant models."""
    from django.apps import apps

    from .models import TenantModel

    links = []
    for model in apps.get_models():
        if not issubclass(model, TenantModel) or model._meta.proxy or not model._meta.managed:
            continue
        for field in model._meta.concrete_fields:
            related = getattr(field, "related_model", None)
            if field.name == "workspace" or not related or not issubclass(related, TenantModel):
                continue
            links.append((model._meta.db_table, field.column, related._meta.db_table))
    return sorted(set(links))


def _ident(name):
    return '"' + name.replace('"', '""') + '"'


def trigger_sql(links):
    """(create statements, trigger names) for the given links."""
    by_child, by_parent = defaultdict(list), defaultdict(list)
    for child, column, parent in links:
        by_child[child].append((column, parent))
        by_parent[parent].append((child, column))
    statements, names = [], []
    for child, fks in sorted(by_child.items()):
        name = f"{PREFIX}_child_{child}"[:63]
        checks = "\n".join(
            f"""  SELECT {_ident(column)}, workspace_id INTO ref, ws FROM {_ident(child)} WHERE id = NEW.id;
  IF FOUND AND ref IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM {_ident(parent)} p WHERE p.id = ref AND p.workspace_id = ws
  ) THEN
    RAISE EXCEPTION 'cross_tenant_fk_violation: {child}.{column}' USING ERRCODE = '23503';
  END IF;"""
            for column, parent in fks
        )
        statements.append(
            f"""CREATE OR REPLACE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE ref uuid; ws uuid;
BEGIN
{checks}
  RETURN NULL;
END $fn$;"""
        )
        statements.append(f"DROP TRIGGER IF EXISTS {name} ON {_ident(child)};")
        statements.append(
            f"CREATE CONSTRAINT TRIGGER {name} AFTER INSERT OR UPDATE ON {_ident(child)} "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {name}();"
        )
        names.append((child, name))
    for parent, refs in sorted(by_parent.items()):
        name = f"{PREFIX}_parent_{parent}"[:63]
        checks = "\n".join(
            f"""  IF EXISTS (SELECT 1 FROM {_ident(child)} c WHERE c.{_ident(column)} = NEW.id
               AND c.workspace_id <> ws) THEN
    RAISE EXCEPTION 'cross_tenant_fk_violation: {child}.{column} left in another workspace'
      USING ERRCODE = '23503';
  END IF;"""
            for child, column in refs
        )
        statements.append(
            f"""CREATE OR REPLACE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE ws uuid;
BEGIN
  SELECT workspace_id INTO ws FROM {_ident(parent)} WHERE id = NEW.id;
  IF NOT FOUND THEN RETURN NULL; END IF;
{checks}
  RETURN NULL;
END $fn$;"""
        )
        statements.append(f"DROP TRIGGER IF EXISTS {name} ON {_ident(parent)};")
        statements.append(
            f"CREATE CONSTRAINT TRIGGER {name} AFTER UPDATE OF workspace_id ON {_ident(parent)} "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            f"WHEN (OLD.workspace_id IS DISTINCT FROM NEW.workspace_id) "
            f"EXECUTE FUNCTION {name}();"
        )
        names.append((parent, name))
    return statements, names


def install(using="default"):
    from django.db import connections

    connection = connections[using]
    if connection.vendor != "postgresql":
        return 0
    statements, names = trigger_sql(tenant_links())
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    return len(names)


def installed(using="default"):
    """{(table, trigger)} present in the database, for the coverage test."""
    from django.db import connections

    with connections[using].cursor() as cursor:
        cursor.execute(
            "SELECT c.relname, t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE t.tgname LIKE %s AND NOT t.tgisinternal",
            [PREFIX + "%"],
        )
        return set(cursor.fetchall())


def on_post_migrate(sender, using="default", **kwargs):
    # post_migrate fires once per app after the whole plan has run; install once.
    if sender.name == "apps.tenants":
        install(using)
