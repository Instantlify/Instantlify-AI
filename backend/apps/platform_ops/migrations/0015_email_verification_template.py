"""Register verification copy without replacing templates edited by an operator."""

from django.db import migrations


def seed(apps, schema_editor):
    apps.get_model("platform_ops", "EmailTemplate").objects.using(
        schema_editor.connection.alias
    ).get_or_create(
        name="email-verification",
        defaults={
            "description": "Sent after registration and when an unverified user requests a new link. Available variables: name, email, link.",
            "subject": "Confirm your Instantlify email address",
            "body": (
                "Hi {{ name }},\n\n"
                "Confirm your email address to finish setting up your Instantlify account:\n\n"
                "{{ link }}\n\n"
                "This link expires in three days. If you did not sign up, you can ignore this email."
            ),
            "status": "active",
        },
    )


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0014_communityreply_parent")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
