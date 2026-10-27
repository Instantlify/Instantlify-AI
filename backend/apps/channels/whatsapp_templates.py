"""Approved WhatsApp templates, with server-derived fields and send-time revalidation."""

import hashlib
import json
import re

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crm.views import conversations_for
from apps.platform_ops.security import assert_enabled

from .media import validate_media
from .transport import ProviderError
from .whatsapp import graph

VARIABLE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def require_whatsapp(connection):
    assert_enabled(connection.workspace_id, "messaging", "integration:whatsapp")
    if (
        settings.CHANNEL_ADAPTER_MODE != "live"
        or connection.provider != "whatsapp"
        or connection.is_test
        or connection.status != "active"
        or connection.expires_at <= timezone.now()
    ):
        raise serializers.ValidationError("Connect an active WhatsApp business number first.")
    if not re.fullmatch(r"[0-9]{1,40}", str(connection.profile.get("waba_id", ""))):
        raise serializers.ValidationError(
            "Reconnect WhatsApp using Connect WhatsApp to load your approved messages."
        )


def template_definition(raw):
    """Unsupported rich formats are shown explicitly; never send incomplete components."""
    fields, parts, buttons = [], [], []
    reason = ""
    components = raw.get("components", [])
    for component in components:
        kind = component.get("type", "").upper()
        text = str(component.get("text", ""))
        if kind in {"HEADER", "BODY", "FOOTER"}:
            if text:
                parts.append(text)
            fmt = component.get("format", "TEXT")
            if kind == "HEADER" and fmt in {"IMAGE", "VIDEO", "DOCUMENT"}:
                fields.append(
                    {
                        "key": "header_media",
                        "label": f"{fmt.title()} link",
                        "type": "url",
                        "max_length": 2000,
                    }
                )
            elif kind == "HEADER" and fmt != "TEXT":
                reason = "This message uses a header that cannot be sent from the inbox yet."
            for name in dict.fromkeys(VARIABLE.findall(text)):
                fields.append(
                    {
                        "key": f"{kind.lower()}_{name}",
                        "label": f"{'Heading' if kind == 'HEADER' else 'Message'} detail {name}"
                        if name.isdigit()
                        else name.replace("_", " ").capitalize(),
                        "type": "text",
                        "max_length": 1024,
                    }
                )
        elif kind == "BUTTONS":
            for index, button in enumerate(component.get("buttons", [])):
                button_type = button.get("type")
                buttons.append(str(button.get("text", "")))
                if button_type == "URL" and VARIABLE.search(button.get("url", "")):
                    fields.append(
                        {
                            "key": f"button_{index}",
                            "label": f"{button.get('text', 'Website')} · link ending",
                            "type": "text",
                            "max_length": 1024,
                        }
                    )
                elif button_type not in {"URL", "PHONE_NUMBER", "QUICK_REPLY"}:
                    reason = "This message uses buttons that cannot be sent from the inbox yet."
        else:
            reason = "This message uses a special format that cannot be sent from the inbox yet."
    if raw.get("category") == "AUTHENTICATION":
        reason = "Verification-code messages must be sent by your secure sign-in service."
    if not any(c.get("type") == "BODY" for c in components):
        reason = "This message has no supported text body."
    # Hash only the definition relevant to sending; review status is checked separately.
    signature = hashlib.sha256(
        json.dumps(
            {
                "name": raw.get("name"),
                "language": raw.get("language"),
                "components": components,
                "parameter_format": raw.get("parameter_format", "POSITIONAL"),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "id": str(raw["id"]),
        "name": raw["name"],
        "language": raw["language"],
        "category": raw.get("category", ""),
        "text": "\n\n".join(parts),
        "preview_parts": [
            {"kind": c["type"].lower(), "text": c["text"]}
            for c in components
            if c.get("type") in {"HEADER", "BODY", "FOOTER"} and c.get("text")
        ],
        "buttons": buttons,
        "fields": fields,
        "supported": not reason,
        "reason": reason,
        "signature": signature,
    }


def catalog(connection, *, name=None):
    require_whatsapp(connection)
    after = None
    results = []
    for _ in range(30):
        params = {
            "fields": "id,name,status,language,category,components,parameter_format",
            "limit": 100,
        }
        if name:
            params["name"] = name
        if after:
            params["after"] = after
        body = graph(
            "GET",
            f"{connection.profile['waba_id']}/message_templates",
            connection.access_token,
            params=params,
        )
        results.extend(item for item in body.get("data", []) if item.get("status") == "APPROVED")
        paging = body.get("paging", {})
        after = paging.get("cursors", {}).get("after") if paging.get("next") else None
        if not after:
            return results
    raise serializers.ValidationError(
        "There are too many messages to load at once. Please try again."
    )


def prepare_template(connection, selection):
    raw = next(
        (
            item
            for item in catalog(connection, name=selection["name"])
            if item.get("name") == selection["name"]
            and item.get("language") == selection["language"]
        ),
        None,
    )
    if not raw:
        raise serializers.ValidationError(
            "This message is no longer approved. Refresh and choose another."
        )
    definition = template_definition(raw)
    if not definition["supported"]:
        raise serializers.ValidationError(definition["reason"])
    if definition["signature"] != selection["signature"]:
        raise serializers.ValidationError(
            "This message changed. Refresh it and check the details again."
        )
    values = selection["values"]
    errors = {}
    for field in definition["fields"]:
        value = values.get(field["key"], "")
        if not isinstance(value, str) or not value.strip() or len(value) > field["max_length"]:
            errors[field["key"]] = (
                f"Enter {field['label'].lower()} (up to {field['max_length']} characters)."
            )
        elif field["type"] == "url":
            try:
                validate_media(value, "image")
            except serializers.ValidationError:
                errors[field["key"]] = "Use a public HTTPS link to your file."
    if set(values) - {field["key"] for field in definition["fields"]}:
        raise serializers.ValidationError("Refresh this message and fill in its current details.")
    if errors:
        raise serializers.ValidationError(errors)
    components = []
    preview = []
    for component in raw["components"]:
        kind = component["type"].lower()
        if kind in {"header", "body", "footer"}:
            text = component.get("text", "")
            names = list(dict.fromkeys(VARIABLE.findall(text)))
            if names:
                parameters = [{"type": "text", "text": values[f"{kind}_{name}"]} for name in names]
                if raw.get("parameter_format") == "NAMED":
                    for name, parameter in zip(names, parameters, strict=True):
                        parameter["parameter_name"] = name
                components.append({"type": kind, "parameters": parameters})
            if kind == "header" and component.get("format") in {"IMAGE", "VIDEO", "DOCUMENT"}:
                media_type = component["format"].lower()
                components.append(
                    {
                        "type": "header",
                        "parameters": [
                            {"type": media_type, media_type: {"link": values["header_media"]}}
                        ],
                    }
                )
                preview.append(f"[{media_type.title()}]")
            if text:
                preview.append(VARIABLE.sub(lambda m, part=kind: values[f"{part}_{m[1]}"], text))
        elif kind == "buttons":
            for index, button in enumerate(component.get("buttons", [])):
                if button["type"] == "URL" and f"button_{index}" in values:
                    components.append(
                        {
                            "type": "button",
                            "sub_type": "url",
                            "index": str(index),
                            "parameters": [{"type": "text", "text": values[f"button_{index}"]}],
                        }
                    )
    return {
        "name": raw["name"],
        "language": {"code": raw["language"]},
        "components": components,
    }, "\n\n".join(preview)


class TemplateSendSerializer(serializers.Serializer):
    name = serializers.RegexField(r"^[a-z0-9_]{1,512}$")
    language = serializers.RegexField(r"^[A-Za-z_]{2,20}$")
    signature = serializers.RegexField(r"^[a-f0-9]{64}$")
    values = serializers.DictField(
        child=serializers.CharField(max_length=2000, allow_blank=True), default=dict
    )
    consent_confirmed = serializers.BooleanField()

    def validate_consent_confirmed(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "Confirm that this customer agreed to receive WhatsApp messages."
            )
        return value


class ConversationTemplatesView(APIView):
    def get(self, request, workspace_id, pk):
        conversation = get_object_or_404(conversations_for(request, workspace_id), pk=pk)
        try:
            results = [
                template_definition(raw) for raw in catalog(conversation.identity.connection)
            ]
        except ProviderError:
            raise serializers.ValidationError(
                "Approved messages could not be loaded. Check your WhatsApp connection and try again."
            ) from None
        return Response({"results": results})

    def post(self, request, workspace_id, pk):
        from apps.crm.services import queue_reply

        conversation = get_object_or_404(conversations_for(request, workspace_id), pk=pk)
        serializer = TemplateSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key):
            raise serializers.ValidationError("Please reopen this message and try sending again.")
        try:
            item = queue_reply(
                conversation,
                "",
                f"human-template:{pk}:{key}",
                actor=request.user,
                whatsapp_template=serializer.validated_data,
            )
        except ProviderError:
            raise serializers.ValidationError(
                "WhatsApp could not check this approved message. Please try again."
            ) from None
        return Response({"id": item.pk, "status": item.status}, status=202)
