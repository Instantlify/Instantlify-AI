from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "0008_integrationjob_form_submission")]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="handoff_reason",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
    ]
