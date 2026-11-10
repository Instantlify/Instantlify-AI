"""Validated CRM actions used by guided flows and the visual canvas alike."""

import json
import re
import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.tenants.models import Membership


def validate_action(data):
    kind = data["kind"]
    from .avatar import validate_avatar

    validate_avatar(data)
    from .calls import validate_call

    validate_call(data)
    from .media_steps import validate_voice

    validate_voice(data)
    from .ai_steps import validate_ai

    validate_ai(data)
    if kind == "send_media":
        from apps.channels.media import validate_media

        validate_media(data.get("media_url"), data.get("media_type"))
    if kind == "integration_action":
        try:
            uuid.UUID(str(data.get("integration_id", "")))
        except ValueError:
            raise ValidationError("Choose a connected integration.") from None
        if not isinstance(data.get("operation"), str) or data["operation"] not in {
            "sync_lead",
            "notify",
            "send_email",
            "webhook",
        }:
            raise ValidationError("Choose a supported integration operation.")
        if not isinstance(data.get("variable", "integration_result"), str) or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]{0,59}", data.get("variable", "integration_result")
        ):
            raise ValidationError("Use a short variable name for the integration result.")
        if data.get("variable") in {"comment_id", "last_text"}:
            raise ValidationError("Choose a result variable that is not reserved by the workflow.")
        if data.get("operation") in {"notify", "send_email"} and (
            not isinstance(data.get("text"), str) or not 1 <= len(data["text"].strip()) <= 2000
        ):
            raise ValidationError("Notification text needs 1–2000 characters.")
        if data.get("operation") == "send_email":
            subject = data.get("subject")
            if (
                not isinstance(subject, str)
                or not 1 <= len(subject.strip()) <= 200
                or "\n" in subject
                or "\r" in subject
            ):
                raise ValidationError("Email subject needs 1–200 characters on one line.")
            if data.get("to") and (
                not isinstance(data["to"], str)
                or len(data["to"]) > 254
                or "\n" in data["to"]
                or "\r" in data["to"]
            ):
                raise ValidationError("Choose a valid email recipient.")
        if data.get("operation") == "webhook":
            try:
                body = data.get("request_body", "{}")
                if (
                    not isinstance(body, str)
                    or len(body) > 10000
                    or not isinstance(json.loads(body), dict)
                ):
                    raise ValueError
            except (ValueError, TypeError):
                raise ValidationError(
                    "Webhook body must be a JSON object up to 10,000 characters."
                ) from None
            mapping = data.get("response_map", {})
            if isinstance(mapping, str):
                try:
                    if len(mapping) > 10000:
                        raise ValueError
                    mapping = json.loads(mapping)
                except (ValueError, TypeError):
                    raise ValidationError("Response mapping must be a JSON object.") from None
            if not isinstance(mapping, dict) or len(mapping) > 20:
                raise ValidationError("Map at most 20 response fields.")
            for variable, path in mapping.items():
                if (
                    not isinstance(variable, str)
                    or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,59}", variable)
                    or variable in {"comment_id", "last_text"}
                    or not isinstance(path, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){0,9}", path)
                    or len(path) > 200
                ):
                    raise ValidationError(
                        "Response mappings need variable names and dotted JSON paths."
                    )
    if kind == "randomizer":
        weight = data.get("percentage", 50)
        if isinstance(weight, bool) or not isinstance(weight, int) or not 0 <= weight <= 100:
            raise ValidationError(
                "The first path's percentage must be a whole number from 0 to 100."
            )
    if kind == "set_stage" and (
        not isinstance(data.get("stage"), str)
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,19}", data["stage"])
    ):
        raise ValidationError("Choose a valid contact stage.")
    if kind == "set_field":
        key, value = data.get("field"), data.get("value")
        if (
            not isinstance(key, str)
            or not 1 <= len(key.strip()) <= 60
            or not isinstance(value, str)
            or len(value) > 500
        ):
            raise ValidationError(
                "A custom field needs a name up to 60 characters and a value up to 500 characters."
            )
    if kind == "add_tag":
        tag = data.get("tag")
        if not isinstance(tag, str) or not 1 <= len(tag.strip()) <= 40:
            raise ValidationError("A tag needs 1–40 characters.")
    if kind == "assign_member":
        value = data.get("user_id")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValidationError("Choose a valid team member.")
    if kind == "transfer":
        try:
            uuid.UUID(str(data.get("automation_id", "")))
        except ValueError:
            raise ValidationError("Choose a destination automation.") from None
    if kind == "capture_email":
        text = data.get("retry_text", "Please reply with a valid email address.")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValidationError("An email retry message needs 1–2000 characters.")
    if kind == "wait" and "expected_reply" in data:
        expected = data["expected_reply"]
        if not isinstance(expected, str) or not 1 <= len(expected.encode()) <= 64:
            raise ValidationError("A reply button needs a valid response payload.")


def validate_workspace_references(graph, workspace_id, automation_id):
    from apps.channels.models import ChannelConnection
    from apps.crm.stages import stage_ids

    from .models import Automation

    stages = stage_ids(workspace_id)
    for node in graph["nodes"]:
        if node["data"]["kind"] == "set_stage" and node["data"]["stage"] not in stages:
            raise ValidationError("Choose a stage from this workspace's pipeline.")
    connection_id = graph.get("connection_id")
    if connection_id:
        try:
            connection_id = uuid.UUID(str(connection_id))
        except ValueError:
            raise ValidationError("Choose a connected account in this workspace.") from None
        connection = (
            ChannelConnection.objects.for_workspace(workspace_id)
            .filter(pk=connection_id, status="active", expires_at__gt=timezone.now())
            .first()
        )
        if not connection or any(
            trigger.get("channel") and trigger["channel"] != connection.provider
            for trigger in graph["triggers"]
        ):
            raise ValidationError("The selected account does not match the flow's channel.")
        from apps.billing.gating import check_connection_unlocked

        check_connection_unlocked(connection)
        if graph.get("comment_post_ids"):
            from apps.channels.adapters import IntegrationUnavailable, adapter_for
            from apps.channels.transport import ProviderError

            try:
                adapter = adapter_for(connection)
                for post_id in graph["comment_post_ids"]:
                    if not adapter.owns_post(post_id):
                        raise ValidationError("A selected post does not belong to this account.")
            except (ProviderError, IntegrationUnavailable):
                raise ValidationError(
                    "The selected posts could not be verified. Reconnect the account and try again."
                ) from None
    for node in graph["nodes"]:
        data = node["data"]
        if data["kind"] == "avatar_video":
            from .avatar import avatar_config

            avatar_config(workspace_id, data)
            if any(
                t.get("channel") not in {"instagram", "messenger", "whatsapp", "telegram"}
                for t in graph["triggers"]
            ):
                raise ValidationError(
                    "Avatar video requires an explicit supported messaging channel."
                )
        if data["kind"] == "ai_call":
            from .calls import call_config

            call_config(workspace_id, data)
        if data["kind"] == "generate_voice":
            from .media_steps import voice_config

            voice_config(workspace_id, data["integration_id"])
            if any(
                t.get("channel") not in {"instagram", "messenger", "whatsapp", "telegram"}
                for t in graph["triggers"]
            ):
                raise ValidationError(
                    "Generated voice requires an explicit supported messaging channel."
                )
        if data["kind"] in {"ai_generate", "ai_extract", "ai_condition", "ai_agent"}:
            from apps.billing.gating import check_feature

            from .ai_steps import model_config

            check_feature(workspace_id, "ai_agent_enabled")
            model_config(workspace_id, data)
        if data["kind"] in {"integration_action", "start_agent"}:
            from apps.billing.gating import check_feature

            check_feature(
                workspace_id,
                "integrations_unlocked"
                if data["kind"] == "integration_action"
                else "ai_agent_enabled",
            )
        if data["kind"] == "integration_action":
            from apps.crm.models import IntegrationConfig

            config = (
                IntegrationConfig.objects.for_workspace(workspace_id)
                .filter(pk=data["integration_id"], enabled=True, status="active")
                .first()
            )
            allowed = {
                "notify": {"slack"},
                "sync_lead": {
                    "airtable",
                    "notion",
                    "attio",
                    "gohighlevel",
                    "google_sheets",
                    "mailerlite",
                    "klaviyo",
                    "systeme_io",
                },
                "send_email": {"gmail", "outlook", "zorromail"},
                "webhook": {"n8n", "make", "discord", "webhook"},
            }
            if not config or config.provider not in allowed[data["operation"]]:
                raise ValidationError("Choose an active integration that supports this operation.")
        if data["kind"] == "start_agent":
            from apps.agents.models import AgentConfig

            if not AgentConfig.objects.for_workspace(workspace_id).filter(enabled=True).exists():
                raise ValidationError(
                    "Enable the workspace AI assistant before publishing this step."
                )
        if (
            data["kind"] == "assign_member"
            and not Membership.objects.for_workspace(workspace_id)
            .filter(user_id=data["user_id"], user__is_active=True)
            .exists()
        ):
            raise ValidationError("The assignee must be an active member of this workspace.")
        if data["kind"] == "transfer":
            if str(data["automation_id"]) == str(automation_id):
                raise ValidationError("An automation cannot transfer to itself.")
            target = (
                Automation.objects.for_workspace(workspace_id)
                .filter(pk=data["automation_id"], enabled=True)
                .exclude(published={})
                .first()
            )
            if not target:
                raise ValidationError("Choose a published, enabled automation in this workspace.")
            if (
                connection_id
                and target.published.get("connection_id")
                and str(connection_id) != str(target.published["connection_id"])
            ):
                raise ValidationError("The destination automation belongs to a different account.")


def capture_email(state, message, data):
    """Invalid replies leave the flow waiting; they never become a CRM email."""
    from apps.crm.models import Lead
    from apps.crm.services import queue_reply

    value = message.text.strip()
    try:
        if len(value) > 254:
            raise DjangoValidationError("Email address is too long.")
        validate_email(value)
    except DjangoValidationError:
        queue_reply(
            state.conversation,
            data.get("retry_text", "Please reply with a valid email address."),
            f"flow:{state.id}:{message.id}:email-retry",
            automation_id=state.automation_id,
        )
        return False
    Lead.objects.for_workspace(state.workspace_id).filter(
        pk=state.conversation.identity.lead_id
    ).update(email=value)
    state.variables["email"] = value
    from apps.crm.services import notify
    from apps.tenants.services import audit

    audit(
        state.conversation.workspace,
        None,
        "automation.email_captured",
        state.conversation.identity.lead_id,
        automation_id=str(state.automation_id),
    )
    transaction.on_commit(lambda: notify(state.workspace_id))
    return True


def apply_action(state, data):
    """Recheck mutable tenant references at execution time, including after a wait."""
    from apps.crm.models import Lead
    from apps.tenants.services import audit

    if data["kind"] in {"add_tag", "set_field", "set_stage"}:
        lead = (
            Lead.objects.for_workspace(state.workspace_id)
            .select_for_update()
            .get(pk=state.conversation.identity.lead_id)
        )
        if data["kind"] == "add_tag":
            tag = data["tag"].strip()
            if tag in lead.tags:
                return
            if tag not in lead.tags:
                if len(lead.tags) >= 50:
                    raise ValidationError("This contact already has 50 tags.")
                lead.tags = [*lead.tags, tag]
            field, event = "tags", "automation.contact_tagged"
        elif data["kind"] == "set_field":
            key, value = data["field"].strip(), data["value"]
            for name, content in state.variables.items():
                value = value.replace("{{" + name + "}}", str(content)[:500])
            if key not in lead.fields and len(lead.fields) >= 50:
                raise ValidationError("This contact already has 50 custom fields.")
            lead.fields = {**lead.fields, key: value[:500]}
            field, event = "fields", "automation.contact_field_updated"
        else:
            lead.stage = data["stage"]
            field, event = "stage", "automation.contact_stage_updated"
        lead.save(update_fields=[field])
        audit(
            state.conversation.workspace,
            None,
            event,
            lead.pk,
            automation_id=str(state.automation_id),
        )
    elif data["kind"] == "assign_member":
        member = (
            Membership.objects.for_workspace(state.workspace_id)
            .filter(user_id=data["user_id"], user__is_active=True)
            .first()
        )
        if not member:
            raise ValidationError("The assignee is no longer a workspace member.")
        state.conversation.assigned_to_id = member.user_id
        state.conversation.save(update_fields=["assigned_to", "updated_at"])
        audit(
            state.conversation.workspace,
            None,
            "automation.conversation_assigned",
            state.conversation_id,
            automation_id=str(state.automation_id),
        )
    from apps.crm.services import notify

    transaction.on_commit(lambda: notify(state.workspace_id))
