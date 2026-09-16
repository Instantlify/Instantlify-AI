from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "CREATE FUNCTION platform_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Platform audit is append-only'; END; $$"
        )
        schema_editor.execute(
            "CREATE TRIGGER platform_audit_immutable BEFORE UPDATE OR DELETE ON platform_ops_platformaudit FOR EACH ROW EXECUTE FUNCTION platform_audit_immutable()"
        )
    elif schema_editor.connection.vendor == "sqlite":
        for operation in ["UPDATE", "DELETE"]:
            schema_editor.execute(
                f"CREATE TRIGGER platform_audit_no_{operation.lower()} BEFORE {operation} ON platform_ops_platformaudit BEGIN SELECT RAISE(ABORT, 'Platform audit is append-only'); END"
            )


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TRIGGER platform_audit_immutable ON platform_ops_platformaudit")
        schema_editor.execute("DROP FUNCTION platform_audit_immutable()")
    elif schema_editor.connection.vendor == "sqlite":
        for operation in ["update", "delete"]:
            schema_editor.execute(f"DROP TRIGGER platform_audit_no_{operation}")


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0001_initial")]
    operations = [migrations.RunPython(install, uninstall)]
