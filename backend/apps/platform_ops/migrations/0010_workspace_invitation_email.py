from django.db import migrations


def seed_invitation_email(apps, schema_editor):
    apps.get_model("platform_ops", "EmailTemplate").objects.get_or_create(
        name="workspace-invitation",
        defaults={
            "description": "Sent when a workspace owner or admin invites a teammate.",
            "subject": "Join {{ workspace }} on Nemio",
            "body": (
                "Hello,\n\n{{ inviter }} invited you to join {{ workspace }} on Nemio "
                "as an {{ role }}.\n\nAccept your invitation:\n{{ link }}\n\n"
                "Sign in or create an account using {{ email }} to accept. "
                "This invitation expires in seven days.\n\n"
                "If you were not expecting this invitation, you can ignore it. "
                "You have not been added to the workspace.\n\nThe Nemio team"
            ),
            "status": "active",
        },
    )


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0009_workspacecapability")]
    operations = [migrations.RunPython(seed_invitation_email, migrations.RunPython.noop)]
