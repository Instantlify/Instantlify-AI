import json
import re
import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.crm.models import Lead
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import DeepLink, FormSubmission, LeadForm


class FormSerializer(serializers.ModelSerializer):
    fields = serializers.JSONField(required=True)
    submissions = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = LeadForm
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "fields",
            "consent_text",
            "success_text",
            "published",
            "created_at",
            "submissions",
        ]
        read_only_fields = ["id", "created_at", "submissions"]

    def validate_slug(self, value):
        value = value.lower()
        query = LeadForm.all_objects.filter(slug=value)
        if self.instance:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise serializers.ValidationError("That form address is already in use.")
        return value

    def validate_fields(self, value):
        if not isinstance(value, list) or not 1 <= len(value) <= 20:
            raise serializers.ValidationError(
                "Add 1–20 fields, including an email field with ID email."
            )
        seen = set()
        for field in value:
            if not isinstance(field, dict) or set(field) - {
                "id",
                "label",
                "type",
                "required",
                "options",
            }:
                raise serializers.ValidationError("Invalid field configuration.")
            key = field.get("id")
            if (
                not isinstance(key, str)
                or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key)
                or key in seen
            ):
                raise serializers.ValidationError(
                    "Use unique lowercase field IDs up to 40 characters."
                )
            seen.add(key)
            if (
                not isinstance(field.get("label"), str)
                or not 1 <= len(field["label"].strip()) <= 120
            ):
                raise serializers.ValidationError("Each field needs a label up to 120 characters.")
            if field.get("type") not in {
                "text",
                "textarea",
                "email",
                "tel",
                "select",
            } or not isinstance(field.get("required", False), bool):
                raise serializers.ValidationError("Unsupported field type or required setting.")
            if field["type"] == "select":
                options = field.get("options")
                if (
                    not isinstance(options, list)
                    or not 1 <= len(options) <= 30
                    or any(not isinstance(v, str) or not 1 <= len(v) <= 120 for v in options)
                ):
                    raise serializers.ValidationError("Select fields need 1–30 text options.")
        email = next((f for f in value if f["id"] == "email"), None)
        if not email or email["type"] != "email" or email.get("required") is not True:
            raise serializers.ValidationError(
                "Include a required email field with ID email for CRM capture."
            )
        return value


class FormList(generics.ListCreateAPIView):
    serializer_class = FormSerializer
    pagination_class = None

    def get_queryset(self):
        from django.db.models import Count

        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return LeadForm.objects.for_workspace(self.kwargs["workspace_id"]).annotate(
            submissions=Count("formsubmission")
        )

    def perform_create(self, serializer):
        member = workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        item = save_form(serializer, workspace=member.workspace)
        audit(member.workspace, self.request.user, "form.created", item.pk)


def save_form(serializer, **kwargs):
    try:
        with transaction.atomic():
            return serializer.save(**kwargs)
    except IntegrityError:
        raise serializers.ValidationError("That form address is already in use.") from None


class FormDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FormSerializer

    def get_queryset(self):
        workspace_membership(self.request, self.kwargs["workspace_id"], ["owner", "admin"])
        return LeadForm.objects.for_workspace(self.kwargs["workspace_id"])

    def perform_update(self, serializer):
        save_form(serializer)


class SubmissionList(APIView):
    def get(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        form = get_object_or_404(LeadForm.objects.for_workspace(workspace_id), pk=pk)
        return Response(
            [
                {
                    "id": row.pk,
                    "lead_id": row.lead_id,
                    "created_at": row.created_at,
                    "answers": json.loads(row.answers),
                    "consent_text": row.consent_text,
                    "link_id": row.link_id,
                }
                for row in FormSubmission.objects.for_workspace(workspace_id).filter(form=form)[
                    :500
                ]
            ]
        )


class FormThrottle(AnonRateThrottle):
    rate = "20/min"


class PublicFormView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [FormThrottle]

    def get(self, request, slug):
        form = get_object_or_404(LeadForm.all_objects, slug=slug, published=True)
        return Response(
            {
                key: getattr(form, key)
                for key in ["title", "description", "fields", "consent_text", "success_text"]
            }
        )

    def post(self, request, slug):
        with transaction.atomic():
            form = get_object_or_404(
                LeadForm.all_objects.select_for_update(), slug=slug, published=True
            )
            from apps.tenants.models import Workspace

            Workspace.objects.select_for_update().get(pk=form.workspace_id)
            if request.data.get("website") or request.data.get("consent") is not True:
                raise serializers.ValidationError("Confirm consent before submitting the form.")
            try:
                request_id = uuid.UUID(str(request.data.get("request_id", "")))
            except ValueError:
                raise serializers.ValidationError("A valid request ID is required.") from None
            old = (
                FormSubmission.objects.for_workspace(form.workspace_id)
                .filter(form=form, request_id=request_id)
                .first()
            )
            if old:
                return Response({"received": True, "message": form.success_text})
            values = request.data.get("answers")
            if not isinstance(values, dict) or set(values) - {f["id"] for f in form.fields}:
                raise serializers.ValidationError("Submit only the fields in this form.")
            answers = {}
            for field in form.fields:
                value = values.get(field["id"], "")
                if not isinstance(value, str) or len(value) > 2000:
                    raise serializers.ValidationError(
                        {field["id"]: "Use up to 2000 text characters."}
                    )
                value = value.strip()
                if field.get("required") and not value:
                    raise serializers.ValidationError({field["id"]: "This field is required."})
                if value and field["type"] == "select" and value not in field["options"]:
                    raise serializers.ValidationError(
                        {field["id"]: "Choose one of the listed options."}
                    )
                if value and field["type"] == "email":
                    try:
                        validate_email(value)
                    except DjangoValidationError:
                        raise serializers.ValidationError(
                            {field["id"]: "Enter a valid email address."}
                        ) from None
                    if len(value) > 254:
                        raise serializers.ValidationError("Email address is too long.")
                answers[field["id"]] = value
            email = answers["email"].lower()
            lead = Lead.objects.for_workspace(form.workspace_id).filter(email__iexact=email).first()
            link = (
                DeepLink.objects.for_workspace(form.workspace_id)
                .filter(code=request.data.get("ref", ""), active=True)
                .first()
                if isinstance(request.data.get("ref", ""), str)
                else None
            )
            if not lead:
                from apps.billing.gating import check_within_limit

                check_within_limit(form.workspace_id, "max_contacts")
                lead = Lead.objects.for_workspace(form.workspace_id).create(
                    workspace_id=form.workspace_id,
                    email=email,
                    name=answers.get("name", "")[:150],
                    fields={
                        "source": "form",
                        "form": str(form.pk),
                        **(
                            {
                                "campaign": link.campaign,
                                "utm_source": link.source,
                                "utm_medium": link.medium,
                            }
                            if link
                            else {}
                        ),
                    },
                )
            FormSubmission.objects.for_workspace(form.workspace_id).create(
                workspace_id=form.workspace_id,
                form=form,
                lead=lead,
                link=link,
                request_id=request_id,
                answers=json.dumps(answers),
                consent_text=form.consent_text,
            )
            # Existing opt-outs remain opted out. Submitting a form never sends a message.
        return Response({"received": True, "message": form.success_text}, status=201)
