from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0003_dailymetric_subscriptionsnapshot")]

    operations = [
        migrations.CreateModel(
            name="PlatformSetting",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("key", models.CharField(max_length=80, unique=True)),
                ("value", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["key"]},
        )
    ]
