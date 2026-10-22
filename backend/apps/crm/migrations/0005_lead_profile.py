from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "0004_message_author")]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="handle",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="lead",
            name="avatar_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="lead",
            name="profile_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lead",
            name="profile_due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["profile_due_at"], name="crm_lead_profile_865bb2_idx"),
        ),
    ]
