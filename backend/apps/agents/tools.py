import json
import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.channels.transport import ProviderError
from apps.crm.models import IntegrationConfig
from apps.tenants.services import audit

from .models import ToolCall

SCHEMAS = {
    "check_calendar_availability": {"start": "string", "end": "string"},
    "book_call": {"start": "string", "end": "string", "email": "string", "name": "string"},
    "update_crm_field": {"field": "string", "value": "string"},
    "send_voice_note": {"text": "string"},
    # The model may only pick an offer ID; the amount comes from the Offer row.
    "create_payment_link": {"offer_id": "string"},
    "handoff_to_human": {"reason": "string"},
}
DESCRIPTIONS = {
    "check_calendar_availability": "Check whether a time range (ISO 8601 with timezone) is free.",
    "book_call": "Propose booking a call; the customer must confirm with a code before it is booked.",
    "update_crm_field": "Record a qualification detail: interest, budget, timeline or company.",
    "send_voice_note": "Send the given text as a voice note.",
    "create_payment_link": "Create a secure checkout link for one of the listed offers.",
    "handoff_to_human": "Hand the conversation to a human teammate (complaints, refunds, anything you cannot resolve).",
}


def definitions(allowed):
    return [
        {
            "type": "function",
            "name": name,
            "description": DESCRIPTIONS.get(name, name.replace("_", " ")),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {key: {"type": value} for key, value in SCHEMAS[name].items()},
                "required": list(SCHEMAS[name]),
                "additionalProperties": False,
            },
        }
        for name in allowed
        if name in SCHEMAS
    ]


def validate_args(name, args):
    if name not in SCHEMAS or not isinstance(args, dict) or set(args) != set(SCHEMAS[name]):
        raise ValueError("invalid_tool_arguments")
    if any(not isinstance(value, str) or len(value) > 2000 for value in args.values()):
        raise ValueError("invalid_tool_arguments")
    if "start" in args:
        start, end = parse_datetime(args["start"]), parse_datetime(args["end"])
        if (
            not start
            or not end
            or timezone.is_naive(start)
            or timezone.is_naive(end)
            or start < timezone.now()
            or not timedelta(minutes=10) <= end - start <= timedelta(hours=8)
        ):
            raise ValueError("invalid_calendar_range")
    if name == "book_call":
        validate_email(args["email"])
    if name == "create_payment_link":
        import uuid

        try:
            uuid.UUID(args["offer_id"])
        except ValueError:
            raise ValueError("invalid_offer_id") from None


def propose(run, name, args, config):
    try:
        if name not in config.allowed_tools:
            raise ValueError("tool_not_allowed")
        validate_args(name, args)
    except (ValueError, ValidationError) as exc:
        # Rejected model intents are part of the audit trail, not silently dropped.
        ToolCall.objects.for_workspace(run.workspace_id).create(
            workspace_id=run.workspace_id,
            run=run,
            name=str(name)[:80],
            input=json.dumps(args, default=str)[:10000],
            output=json.dumps(
                {
                    "error": str(exc.args[0])[:50]
                    if isinstance(exc, ValueError) and exc.args
                    else "invalid_tool_arguments"
                }
            ),
            status="rejected",
        )
        audit(run.workspace, None, "agent.tool_rejected", run.id)
        raise
    call = ToolCall.objects.for_workspace(run.workspace_id).create(
        workspace_id=run.workspace_id,
        run=run,
        name=name,
        input=json.dumps(args),
        status="awaiting_confirmation" if name == "book_call" else "pending",
        confirmation_code=secrets.token_hex(3) if name == "book_call" else "",
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    if name == "book_call":
        return f"To confirm a call from {args['start']} to {args['end']} for {args['email']}, reply exactly: confirm {call.confirmation_code}"
    return execute(call, config)


def execute(call, config, *, customer_message=None):
    from apps.platform_ops.security import assert_enabled

    assert_enabled(config.workspace_id, "ai")
    from apps.crm.integrations import integration_for

    with transaction.atomic():
        call = ToolCall.objects.for_workspace(call.workspace_id).select_for_update().get(pk=call.pk)
        if call.status == "complete":
            return json.loads(call.output)
        if call.name not in config.allowed_tools or call.status not in {
            "pending",
            "awaiting_confirmation",
        }:
            raise ValueError("tool_execution_guard")
        if call.name == "book_call" and (
            not customer_message
            or customer_message.conversation_id != call.run.message.conversation_id
            or customer_message.text.strip().casefold() != f"confirm {call.confirmation_code}"
            or call.expires_at <= timezone.now()
        ):
            raise ValueError("explicit_customer_confirmation_required")
        args = json.loads(call.input)
        validate_args(call.name, args)
        call.status = "executing"
        call.save()
    try:
        conversation = call.run.message.conversation
        if call.name in {"check_calendar_availability", "book_call"}:
            integration = (
                IntegrationConfig.objects.for_workspace(call.workspace_id)
                .filter(provider__in=["google_calendar", "calcom"], enabled=True)
                .first()
            )
            if not integration:
                raise ValueError("calendar_not_connected")
            adapter = integration_for(integration)
            if call.name == "book_call":
                availability = adapter.execute(
                    "check_calendar_availability",
                    {"start": args["start"], "end": args["end"]},
                    str(call.id),
                )
                if not availability.get("available"):
                    raise ValueError("slot_unavailable")
            result = adapter.execute(call.name, args, str(call.id))
        elif call.name == "create_payment_link":
            from apps.billing.models import Offer
            from apps.billing.payments import create_checkout

            offer = (
                Offer.objects.for_workspace(call.workspace_id)
                .filter(pk=args["offer_id"], active=True)
                .first()
            )
            if not offer:
                raise ValueError("offer_not_found")
            payment = create_checkout(offer, conversation, f"tool:{call.id}")
            result = {
                "payment_id": str(payment.id),
                "checkout_url": payment.checkout_url,
                "amount_cents": payment.amount_cents,
                "currency": payment.currency,
            }
        elif call.name == "handoff_to_human":
            from .runtime import hand_off

            hand_off(conversation, reason=args["reason"][:60] or "agent_requested")
            result = {"handed_off": True}
        elif call.name == "update_crm_field":
            if args["field"] not in {"interest", "budget", "timeline", "company"}:
                raise ValueError("crm_field_not_allowed")
            lead = conversation.identity.lead
            lead.fields = {**lead.fields, args["field"]: args["value"]}
            lead.save(update_fields=["fields"])
            result = {"updated": args["field"]}
        else:
            from .voice import queue_voice

            result = queue_voice(conversation, args["text"], str(call.id))
    except (ProviderError, ValueError, ValidationError) as exc:
        call.status = "failed"
        reason = getattr(exc, "code", None)
        if not reason and isinstance(exc, ValueError) and exc.args:
            reason = str(exc.args[0])[:50]
        call.output = json.dumps({"error": reason or "tool_guard_or_configuration"})
        call.save()
        raise
    call.status = "complete"
    call.output = json.dumps(result)
    call.save()
    audit(call.workspace, None, "agent.tool_completed", call.id)
    if call.name == "book_call":
        from apps.analytics.services import attribution, record

        record(
            call.workspace_id,
            "booked",
            key=f"booked:{call.id}",
            provider=conversation.identity.connection.provider,
            lead_id=conversation.identity.lead_id,
            conversation_id=conversation.pk,
            **attribution(conversation),
        )
    return result
