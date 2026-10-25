"""Import a configured Jotform's contacts without inventing chat consent."""

import re

from django.core.exceptions import ValidationError as InvalidEmail
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gating import check_feature, check_within_limit
from apps.channels.transport import ProviderError, request
from apps.crm.integrations import credentials_for
from apps.tenants.models import Workspace
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import IntegrationConfig, Lead


def form_contacts(config):
    fields = config.options
    if not all(
        re.fullmatch(r"[0-9]{1,30}", str(fields.get(key, "")))
        for key in ["form_id", "email_question"]
    ):
        raise ProviderError("jotform_mapping_missing")
    name_question = str(fields.get("name_question") or "")
    if name_question and not re.fullmatch(r"[0-9]{1,30}", name_question):
        raise ProviderError("jotform_mapping_invalid")
    token = credentials_for(config).get("api_key")
    if not token or config.is_test:
        raise ProviderError("jotform_live_credentials_required")
    region = fields.get("region", "us")
    host = {
        "us": "api.jotform.com",
        "eu": "eu-api.jotform.com",
        "hipaa": "hipaa-api.jotform.com",
    }.get(region)
    if not host:
        raise ProviderError("jotform_region_invalid")
    rows = []
    for offset in range(0, 501, 100):
        body = request(
            "GET",
            f"https://{host}/form/{fields['form_id']}/submissions",
            headers={"APIKEY": token},
            params={"offset": offset, "limit": 100, "orderby": "created_at"},
        )
        if body.get("responseCode") != 200 or not isinstance(body.get("content"), list):
            raise ProviderError("jotform_import_failed")
        batch = body["content"]
        rows.extend(batch)
        if len(rows) > 500:
            raise ProviderError("jotform_import_too_large")
        if len(batch) < 100:
            break
    contacts, skipped = [], 0
    for row in rows:
        answers = row.get("answers", {})
        email = answers.get(str(fields["email_question"]), {}).get("answer", "")
        name = answers.get(name_question, {}).get("answer", "")
        if isinstance(name, dict):
            name = " ".join(str(name.get(part) or "") for part in ["first", "last"]).strip()
        try:
            if not isinstance(email, str):
                raise InvalidEmail("Invalid email")
            validate_email(email)
        except InvalidEmail:
            skipped += 1
            continue
        contacts.append({"email": email.strip().lower(), "name": str(name or "")[:150]})
    return contacts, skipped


class ImportFormContactsView(APIView):
    def post(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        check_feature(workspace_id, "integrations_unlocked")
        config = get_object_or_404(
            IntegrationConfig.objects.for_workspace(workspace_id),
            pk=pk,
            provider="jotform",
            enabled=True,
            status="active",
        )
        try:
            contacts, skipped = form_contacts(config)
        except (ProviderError, KeyError, TypeError, ValueError):
            raise serializers.ValidationError(
                "Could not import this form. Check the API key, form ID, question IDs and region. Import at most 500 submissions per form."
            ) from None
        created = updated = 0
        with transaction.atomic():
            Workspace.objects.select_for_update().get(pk=workspace_id)
            for contact in contacts:
                lead = (
                    Lead.objects.for_workspace(workspace_id)
                    .filter(email__iexact=contact["email"])
                    .first()
                )
                if lead:
                    if not lead.name and contact["name"]:
                        lead.name = contact["name"]
                        lead.save(update_fields=["name"])
                    updated += 1
                else:
                    check_within_limit(workspace_id, "max_contacts")
                    Lead.objects.for_workspace(workspace_id).create(
                        workspace_id=workspace_id, **contact
                    )
                    created += 1
            audit(member.workspace, request.user, "jotform.contacts_imported", config.pk)
        return Response({"created": created, "matched_existing": updated, "skipped": skipped})
