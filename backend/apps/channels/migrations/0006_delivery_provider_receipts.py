from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("channels", "0005_channelconnection_profile")]
    operations = [
        migrations.AddField(
            model_name="delivery",
            name="provider_status",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="delivery",
            name="provider_status_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
