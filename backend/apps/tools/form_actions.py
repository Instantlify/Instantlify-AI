"""Consent-bound form triggers into durable integration actions."""

import json
import uuid

from django.utils import timezone
from rest_framework import serializers

from apps.billing.gating import check_feature
from apps.crm.models import IntegrationConfig, IntegrationJob
from apps.public_api.services import lead_payload

from .form_files import answer_metadata

OPERATIONS = {
    "send_email": {"gmail", "outlook", "zorromail"},
    "sync_lead": {
        "airtable",
        "notion",
        "gohighlevel",
        "attio",
        "google_sheets",
        "mailerlite",
        "klaviyo",
        "systeme_io",
        "mailchimp",
        "beehiiv",
        "kit",
    },
    "notify": {"slack"},
    "webhook": {"n8n", "make", "webhook"},
}


def validate_actions(value, workspace_id):
    if not isinstance(value, list) or len(value) > 5:
        raise serializers.ValidationError("Use up to five actions per submission.")
    if value:
        check_feature(workspace_id, "integrations_unlocked")
    result = []
    for action in value:
        if not isinstance(action, dict) or set(action) - {
            "integration_id",
            "operation",
            "text",
            "subject",
        }:
            raise serializers.ValidationError("Invalid submission action.")
        operation = action.get("operation")
        if operation not in OPERATIONS:
            raise serializers.ValidationError("Choose email, CRM sync, notification or webhook.")
        try:
            integration_id = str(uuid.UUID(str(action.get("integration_id", ""))))
        except ValueError:
            raise serializers.ValidationError("Choose a connected integration.") from None
        if (
            not IntegrationConfig.objects.for_workspace(workspace_id)
            .filter(
                pk=integration_id, provider__in=OPERATIONS[operation], enabled=True, status="active"
            )
            .exists()
        ):
            raise serializers.ValidationError(
                "Choose an active integration compatible with this action."
            )
        text, subject = action.get("text", ""), action.get("subject", "")
        if (
            not isinstance(text, str)
            or len(text) > 2000
            or (operation in {"send_email", "notify"} and not text.strip())
        ):
            raise serializers.ValidationError(
                "Email and notification text needs 1–2000 characters."
            )
        if (
            not isinstance(subject, str)
            or len(subject) > 200
            or "\n" in subject
            or "\r" in subject
            or (operation == "send_email" and not subject.strip())
        ):
            raise serializers.ValidationError(
                "Emails need a one-line subject up to 200 characters."
            )
        result.append(
            {
                "integration_id": integration_id,
                "operation": operation,
                "text": text,
                "subject": subject,
            }
        )
    return result


def queue_submission_actions(submission, form, lead, answers):
    answers = answer_metadata(answers)

    def render(text, limit):
        for key, value in answers.items():
            rendered = (
                value.get("name") or ", ".join(str(item) for item in value.values() if item)
                if isinstance(value, dict)
                else ", ".join(value)
                if isinstance(value, list)
                else value
            )
            text = text.replace("{{" + key + "}}", rendered)
        return text[:limit]

    errors = []
    for index, action in enumerate(form.submission_actions):
        config = (
            IntegrationConfig.objects.for_workspace(form.workspace_id)
            .filter(pk=action["integration_id"])
            .first()
        )
        if not config:
            errors.append({"action": index + 1, "error": "integration_unavailable"})
            continue
        if not lead and action["operation"] not in {"notify", "webhook"}:
            errors.append({"action": index + 1, "error": "contact_required"})
            continue
        payload = lead_payload(lead) if lead else {}
        payload.update(
            to=answers["email"],
            email=answers["email"],
            name=answers.get("name", lead.name if lead else "")
            if isinstance(answers.get("name", lead.name if lead else ""), str)
            else lead.name
            if lead
            else "",
            text=render(action.get("text", ""), 2000),
            subject=" ".join(render(action.get("subject", ""), 200).splitlines()),
        )
        if action["operation"] == "webhook":
            payload["request"] = {
                "event": "form.submitted",
                "form_id": str(form.pk),
                "submission_id": str(submission.pk),
                "answers": answers,
                "lead_id": str(lead.pk) if lead else None,
                "consent_text": submission.consent_text,
            }
        IntegrationJob.objects.for_workspace(form.workspace_id).get_or_create(
            idempotency_key=f"form:{submission.pk}:{index}",
            defaults={
                "workspace_id": form.workspace_id,
                "integration": config,
                "form_submission": submission,
                "operation": action["operation"],
                "payload": json.dumps(payload, default=str),
                "available_at": timezone.now(),
            },
        )
    if errors:
        submission.action_errors = errors
        submission.save(update_fields=["action_errors"])
