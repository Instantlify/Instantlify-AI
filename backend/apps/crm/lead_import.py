"""CSV contact import.

Columns are matched by header, case-insensitively: name (or first/last name), email,
phone, handle/username/instagram, tags (separated by , ; or |) and stage. Every other
column becomes a custom field. A row whose email already belongs to a contact updates
that contact (tags and fields are merged, blank values never overwrite), so importing
the same file twice changes nothing. The whole file is checked against the plan's
contact limit before anything is written.
"""

import csv
import io
import re

from django.core.validators import validate_email
from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import Lead

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
ALIASES = {
    "name": "name",
    "full name": "name",
    "full_name": "name",
    "contact name": "name",
    "first name": "first_name",
    "first_name": "first_name",
    "firstname": "first_name",
    "last name": "last_name",
    "last_name": "last_name",
    "lastname": "last_name",
    "email": "email",
    "email address": "email",
    "e-mail": "email",
    "phone": "phone",
    "phone number": "phone",
    "mobile": "phone",
    "whatsapp": "phone",
    "handle": "handle",
    "username": "handle",
    "instagram": "handle",
    "tags": "tags",
    "tag": "tags",
    "labels": "tags",
    "stage": "stage",
    "status": "stage",
}
FIELD_KEY = re.compile(r"[^a-z0-9_]+")


def _field_key(header):
    return FIELD_KEY.sub("_", header.strip().lower()).strip("_")[:60]


def parse(upload):
    if not upload or upload.size > MAX_BYTES:
        raise serializers.ValidationError("Upload a CSV file of up to 2 MB.")
    raw = upload.read(MAX_BYTES + 1)
    # latin-1 decodes any byte sequence, so `text` is always set.
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)
    if not rows or not any(cell.strip() for cell in rows[0]):
        raise serializers.ValidationError("The file needs a header row.")
    headers = [cell.strip() for cell in rows[0]]
    body = [row for row in rows[1:] if any(cell.strip() for cell in row)]
    if len(body) > MAX_ROWS:
        raise serializers.ValidationError(f"Import up to {MAX_ROWS} contacts per file.")
    columns = []
    for header in headers:
        role = ALIASES.get(header.lower())
        columns.append(role or ("field:" + _field_key(header) if _field_key(header) else None))
    if not {"name", "first_name", "email", "phone", "handle"} & set(columns):
        raise serializers.ValidationError("Include at least a name, email, phone or handle column.")
    return columns, body


def read_row(columns, row, stages):
    """(contact dict, error). Values are trimmed; blanks are dropped."""
    data = {"tags": [], "fields": {}}
    first = last = ""
    for role, cell in zip(columns, row, strict=False):
        value = cell.strip()
        if not role or not value:
            continue
        if role == "first_name":
            first = value
        elif role == "last_name":
            last = value
        elif role == "tags":
            data["tags"] = [t.strip()[:40] for t in re.split(r"[;,|]", value) if t.strip()]
        elif role == "phone":
            data["fields"]["phone"] = value[:40]
        elif role.startswith("field:"):
            data["fields"][role[6:]] = value[:500]
        else:
            data[role] = value
    if not data.get("name") and (first or last):
        data["name"] = f"{first} {last}".strip()
    if data.get("email"):
        data["email"] = data["email"].lower()
        try:
            validate_email(data["email"])
        except Exception:
            return None, "invalid email"
    if data.get("stage"):
        data["stage"] = data["stage"].lower()
        if data["stage"] not in stages:
            return None, "unknown stage"
    if not (
        data.get("name") or data.get("email") or data["fields"].get("phone") or data.get("handle")
    ):
        return None, "no name, email, phone or handle"
    data["name"] = data.get("name", "")[:150]
    data["handle"] = data.get("handle", "")[:150]
    data["tags"] = list(dict.fromkeys(data["tags"]))[:50]
    if len(data["fields"]) > 50:
        return None, "too many custom fields"
    return data, None


def merge(lead, data, extra_tags):
    changed = False
    for attr in ("name", "handle"):
        if data.get(attr) and not getattr(lead, attr):
            setattr(lead, attr, data[attr])
            changed = True
    if data.get("stage") and data["stage"] != lead.stage:
        lead.stage = data["stage"]
        changed = True
    tags = list(dict.fromkeys([*lead.tags, *data["tags"], *extra_tags]))[:50]
    if tags != lead.tags:
        lead.tags = tags
        changed = True
    fields = {**lead.fields, **data["fields"]}
    if fields != lead.fields and len(fields) <= 50:
        lead.fields = fields
        changed = True
    return changed


class LeadImportView(APIView):
    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        workspace = member.workspace
        extra = str(request.data.get("tag") or "").strip()
        if len(extra) > 40:
            raise serializers.ValidationError("The import tag can have at most 40 characters.")
        extra_tags = [extra] if extra else []
        columns, body = parse(request.FILES.get("file"))
        from .stages import stage_ids

        stages = stage_ids(workspace.pk)
        parsed, errors = [], []
        for number, row in enumerate(body, start=2):
            data, error = read_row(columns, row, stages)
            if error:
                errors.append({"row": number, "reason": error})
            else:
                parsed.append(data)
        from apps.billing.gating import check_within_limit
        from apps.tenants.models import Workspace

        created = updated = unchanged = 0
        with transaction.atomic():
            Workspace.objects.select_for_update().get(pk=workspace.pk)
            leads = Lead.objects.for_workspace(workspace)
            emails = {d["email"] for d in parsed if d.get("email")}
            existing = (
                {
                    lead.email.lower(): lead
                    for lead in leads.filter(email__in=emails).select_for_update()
                }
                if emails
                else {}
            )
            seen, new = set(), []
            for data in parsed:
                email = data.get("email", "")
                if email and email in existing:
                    if merge(existing[email], data, extra_tags):
                        existing[email].save()
                        updated += 1
                    else:
                        unchanged += 1
                    continue
                if email and email in seen:
                    unchanged += 1
                    continue
                seen.add(email)
                new.append(data)
            check_within_limit(workspace.pk, "max_contacts", adding=len(new))
            Lead.objects.for_workspace(workspace).bulk_create(
                [
                    Lead(
                        workspace=workspace,
                        name=data["name"],
                        email=data.get("email", ""),
                        handle=data["handle"],
                        stage=data.get("stage", "new"),
                        tags=list(dict.fromkeys([*data["tags"], *extra_tags]))[:50],
                        fields=data["fields"],
                    )
                    for data in new
                ]
            )
            created = len(new)
            audit(workspace, request.user, "leads.imported", workspace.pk)
        return Response(
            {
                "created": created,
                "updated": updated,
                "unchanged": unchanged,
                "skipped": len(errors),
                "errors": errors[:20],
            }
        )
