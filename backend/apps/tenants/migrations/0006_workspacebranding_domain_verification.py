from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0005_user_ban"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspacebranding",
            name="custom_domain_status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("active", "Active"), ("failed", "Failed")],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="workspacebranding",
            name="verification_token",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="workspacebranding",
            name="verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workspacebranding",
            name="tls_status",
            field=models.CharField(
                choices=[
                    ("inactive", "Inactive"),
                    ("issuing", "Issuing"),
                    ("active", "Active"),
                    ("error", "Error"),
                ],
                default="inactive",
                max_length=20,
            ),
        ),
    ]
