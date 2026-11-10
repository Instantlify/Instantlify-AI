"""Typed custom contact fields.

A workspace defines up to 30 fields (text, number, date, dropdown, URL, email). Values
for a defined key are checked against its type whenever a contact is saved through the
API; keys without a definition stay free-form, as before, so existing data and
integrations keep working. Flow conditions read the stored values as usual.
"""

import re
from datetime import date

from django.core.validators import URLValidator, validate_email
from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

TYPES = {"text", "number", "date", "select", "url", "email"}
KEY = re.compile(r"[a-z][a-z0-9_]{0,39}")
MAX_FIELDS = 30
RESERVED = {"source", "phone_verified"}


def definitions_for(workspace_id):
    from apps.tenants.models import Workspace

    return (
        Workspace.objects.filter(pk=workspace_id).values_list("custom_fields", flat=True).first()
        or []
    )


def validate_definitions(value):
    if not isinstance(value, list) or len(value) > MAX_FIELDS:
        raise serializers.ValidationError(f"Define up to {MAX_FIELDS} fields.")
    cleaned, seen = [], set()
    for item in value:
        if not isinstance(item, dict):
            raise serializers.ValidationError("Each field needs a key, label and type.")
        key, label, kind = item.get("key"), item.get("label"), item.get("type")
        if not isinstance(key, str) or not KEY.fullmatch(key) or key in RESERVED:
            raise serializers.ValidationError(
                "Field keys use lowercase letters, digits and _ (up to 40 characters)."
            )
        if key in seen:
            raise serializers.ValidationError("Field keys must be unique.")
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 60:
            raise serializers.ValidationError("Each field needs a label of 1–60 characters.")
        if kind not in TYPES:
            raise serializers.ValidationError("Choose a field type.")
        definition = {"key": key, "label": label.strip(), "type": kind}
        if kind == "select":
            options = item.get("options")
            if (
                not isinstance(options, list)
                or not 1 <= len(options) <= 30
                or any(not isinstance(o, str) or not 1 <= len(o.strip()) <= 60 for o in options)
            ):
                raise serializers.ValidationError("A dropdown needs 1–30 options.")
            definition["options"] = list(dict.fromkeys(o.strip() for o in options))
        seen.add(key)
        cleaned.append(definition)
    return cleaned


def coerce_value(definition, value):
    """The stored form of `value` for this field; raises with a readable message."""
    label = definition["label"]
    text = str(value).strip()
    if text == "":
        return ""
    kind = definition["type"]
    if kind == "number":
        try:
            number = float(text)
        except ValueError:
            raise serializers.ValidationError(f"{label} must be a number.") from None
        return str(int(number)) if number.is_integer() else str(number)
    if kind == "date":
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            raise serializers.ValidationError(f"{label} must be a date (YYYY-MM-DD).") from None
    if kind == "select":
        match = next((o for o in definition["options"] if o.casefold() == text.casefold()), None)
        if match is None:
            raise serializers.ValidationError(f"{label} must be one of its options.")
        return match
    if kind == "url":
        try:
            URLValidator(schemes=["http", "https"])(text)
        except Exception:
            raise serializers.ValidationError(f"{label} must be a web address.") from None
        return text
    if kind == "email":
        try:
            validate_email(text)
        except Exception:
            raise serializers.ValidationError(f"{label} must be an email address.") from None
        return text.lower()
    return text


def coerce_fields(workspace_id, fields):
    definitions = {d["key"]: d for d in definitions_for(workspace_id)}
    return {
        key: coerce_value(definitions[key], value) if key in definitions else value
        for key, value in fields.items()
    }


class CustomFieldsView(APIView):
    def get(self, request, workspace_id):
        member = workspace_membership(request, workspace_id)
        return Response({"fields": definitions_for(member.workspace_id)})

    def put(self, request, workspace_id):
        from apps.tenants.models import Workspace

        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        fields = validate_definitions(request.data.get("fields"))
        with transaction.atomic():
            workspace = Workspace.objects.select_for_update().get(pk=member.workspace_id)
            workspace.custom_fields = fields
            workspace.save(update_fields=["custom_fields"])
            audit(workspace, request.user, "custom_fields.updated", workspace.pk)
        return Response({"fields": fields})
