import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill(apps, schema_editor):
    Lead = apps.get_model("crm", "Lead")
    Membership = apps.get_model("tenants", "Membership")
    Notification = apps.get_model("crm", "AssignmentNotification")
    for lead in Lead._base_manager.exclude(assigned_to_id=None).iterator():
        if Membership.objects.filter(
            workspace_id=lead.workspace_id, user_id=lead.assigned_to_id
        ).exists():
            Notification.objects.create(
                workspace_id=lead.workspace_id, lead_id=lead.pk, recipient_id=lead.assigned_to_id
            )


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0010_lead_assigned_to"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="AssignmentNotification",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="tenants.workspace"
                    ),
                ),
                (
                    "lead",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="crm.lead"),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignment_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_assignment_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["workspace", "recipient", "read_at"], name="assignment_unread_idx"
                    )
                ],
            },
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
