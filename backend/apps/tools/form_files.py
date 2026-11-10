"""Consent-bound file answers; bytes stay in the encrypted submission payload."""

import base64
import binascii
import hashlib
import json
import re

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from rest_framework import serializers
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership

from .models import FormSubmission

MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 2 * MAX_FILE_BYTES


def clean_file(field, value):
    def reject(message):
        raise serializers.ValidationError({field["id"]: message})

    if value in (None, ""):
        if field.get("required"):
            reject("Add a file or signature before submitting.")
        return ""
    if not isinstance(value, dict) or set(value) != {"name", "data"}:
        reject("Choose a file or draw your signature.")
    if not isinstance(value["name"], str) or not 1 <= len(value["name"]) <= 200:
        reject("Use a filename up to 200 characters.")
    if not isinstance(value["data"], str) or len(value["data"]) > ((MAX_FILE_BYTES + 2) // 3) * 4:
        reject("Each file must be no larger than 1 MB.")
    try:
        data = base64.b64decode(value["data"], validate=True)
    except (ValueError, binascii.Error):
        reject("The file could not be read. Choose it again.")
    if not data or len(data) > MAX_FILE_BYTES:
        reject("Choose a nonempty file up to 1 MB.")
    if field["type"] == "signature" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        reject("Draw a signature using the signature pad.")
    name = value["name"].replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip() or "attachment"
    return {
        "name": name,
        "data": base64.b64encode(data).decode(),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def answer_metadata(answers, *, download_prefix=None):
    result = {}
    for key, value in answers.items():
        if isinstance(value, dict) and ("data" in value or "sha256" in value):
            value = {item: value[item] for item in ("name", "size", "sha256") if item in value}
            if download_prefix:
                value["download_url"] = f"{download_prefix}{key}/file/"
        result[key] = value
    return result


class FormFileDownload(APIView):
    def get(self, request, workspace_id, pk, submission_id, field_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        row = get_object_or_404(
            FormSubmission.objects.for_workspace(workspace_id), pk=submission_id, form_id=pk
        )
        value = json.loads(row.answers).get(field_id)
        if not isinstance(value, dict) or not value.get("data"):
            from django.http import Http404

            raise Http404
        response = HttpResponse(
            base64.b64decode(value["data"]), content_type="application/octet-stream"
        )
        response["Content-Disposition"] = content_disposition_header(True, value["name"])
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox"
        return response
