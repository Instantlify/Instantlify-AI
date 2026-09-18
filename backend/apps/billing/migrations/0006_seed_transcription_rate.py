from django.db import migrations

# Transcription is priced per second of audio. The rate card stores cents per million
# units, so for whisper-1 a unit is one second: OpenAI's $0.006/min is 10,000 cents per
# million seconds. Without this row, audio seconds would be priced at the token fallback
# and billed at a fraction of their cost. Editable in the console like any other rate.
PATTERN = "whisper-1"


def seed(apps, schema_editor):
    ModelPricingRate = apps.get_model("billing", "ModelPricingRate")
    ModelPricingRate.objects.get_or_create(
        model_pattern=PATTERN,
        defaults={
            "label": "OpenAI whisper-1 (units are seconds of audio)",
            "our_input": 20000,
            "real_input": 10000,
        },
    )


def unseed(apps, schema_editor):
    apps.get_model("billing", "ModelPricingRate").objects.filter(model_pattern=PATTERN).delete()


class Migration(migrations.Migration):
    dependencies = [("billing", "0005_ai_credits")]

    operations = [migrations.RunPython(seed, unseed)]
