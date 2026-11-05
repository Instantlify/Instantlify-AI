import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0008_supportticket_reporter_supportticketmessage")]

    operations = [
        migrations.CreateModel(
            name="WorkspaceCapability",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("key", models.CharField(max_length=100)),
                ("enabled", models.BooleanField(default=False)),
                ("reason", models.CharField(max_length=300)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="tenants.workspace"
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("workspace", "key"), name="unique_workspace_capability"
                    )
                ]
            },
        ),
    ]
