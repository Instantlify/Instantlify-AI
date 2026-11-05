from django.db import migrations, models


def mark_unfinished_checkouts(apps, schema_editor):
    db = schema_editor.connection.alias
    Workspace = apps.get_model("tenants", "Workspace")
    BillingJob = apps.get_model("billing", "BillingJob")
    BillingAccount = apps.get_model("billing", "BillingAccount")
    attempted = BillingJob._base_manager.using(db).filter(
        kind="checkout", return_to="onboarding"
    )
    subscribed = BillingAccount._base_manager.using(db).exclude(subscription_id="")
    Workspace.objects.using(db).filter(
        pk__in=attempted.values("workspace_id")
    ).exclude(pk__in=subscribed.values("workspace_id")).update(checkout_pending=True)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0007_billing_job_return_to"),
        ("tenants", "0009_workspacebranding_logo_content_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspace",
            name="checkout_pending",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_unfinished_checkouts, migrations.RunPython.noop),
    ]
