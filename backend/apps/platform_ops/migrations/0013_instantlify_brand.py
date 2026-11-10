"""Rename untouched platform defaults without overwriting custom tenant branding."""

import importlib

from django.db import migrations


def rebrand_defaults(apps, schema_editor):
    alias = schema_editor.connection.alias
    templates = apps.get_model("platform_ops", "EmailTemplate").objects.using(alias)
    seed = importlib.import_module("apps.platform_ops.migrations.0006_seed_growth_content")
    for name, _description, subject, body, _status in seed.TEMPLATES:
        row = templates.filter(name=name).first()
        if not row:
            continue
        changes = {}
        for field, original in (("subject", subject), ("body", body)):
            if getattr(row, field) == original:
                changes[field] = original.replace("Nemio", "Instantlify")
        if changes:
            templates.filter(pk=row.pk).update(**changes)
    invitation_defaults = {
        "subject": "Join {{ workspace }} on Nemio",
        "body": (
            "Hello,\n\n{{ inviter }} invited you to join {{ workspace }} on Nemio "
            "as an {{ role }}.\n\nAccept your invitation:\n{{ link }}\n\n"
            "Sign in or create an account using {{ email }} to accept. "
            "This invitation expires in seven days.\n\n"
            "If you were not expecting this invitation, you can ignore it. "
            "You have not been added to the workspace.\n\nThe Nemio team"
        ),
    }
    for field, original in invitation_defaults.items():
        templates.filter(name="workspace-invitation", **{field: original}).update(
            **{field: original.replace("Nemio", "Instantlify")}
        )
    branding = apps.get_model("tenants", "WorkspaceBranding")._base_manager.using(alias)
    branding.filter(brand_name__in=["Nemio", "Nemio AI"], logo_url="", logo_data=b"").update(
        brand_name="Instantlify"
    )


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0012_affiliateaccount"), ("tenants", "0012_profilephoto")]
    operations = [migrations.RunPython(rebrand_defaults, migrations.RunPython.noop)]
