from django.db import migrations


def mark_abandoned_plan_selection(apps, schema_editor):
    db = schema_editor.connection.alias
    Workspace = apps.get_model("tenants", "Workspace")
    BillingAccount = apps.get_model("billing", "BillingAccount")
    SignupFunnelEvent = apps.get_model("platform_ops", "SignupFunnelEvent")
    payment = SignupFunnelEvent.objects.using(db).filter(
        flow="wizard", step="payment", is_owner=True, workspace__isnull=False
    )
    reached = payment.filter(status="reached").values("workspace_id")
    completed = payment.filter(status="completed").values("workspace_id")
    subscribed = BillingAccount._base_manager.using(db).exclude(subscription_id="")
    Workspace.objects.using(db).filter(pk__in=reached).exclude(pk__in=completed).exclude(
        pk__in=subscribed.values("workspace_id")
    ).update(checkout_pending=True)


class Migration(migrations.Migration):
    dependencies = [
        ("platform_ops", "0005_billingauditrun_blogcategory_emailtemplate_and_more"),
        ("tenants", "0010_workspace_checkout_pending"),
    ]

    operations = [
        migrations.RunPython(mark_abandoned_plan_selection, migrations.RunPython.noop),
    ]
