import json
import re
import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.crm.models import IntegrationJob, Lead
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .form_contacts import contact_values
from .form_files import answer_metadata
from .form_schema import clean_answers, validate_branching, validate_fields
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
            "submission_actions",
            "branching",
            "theme",
            "redirect_url",
            "submission_tags",
            "button_align",
            "closed",
            "capture_contacts",
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

    def validate_submission_actions(self, value):
        from .form_actions import validate_actions

        workspace_id = (
            self.instance.workspace_id
            if self.instance
            else self.context["view"].kwargs["workspace_id"]
        )
        return validate_actions(value, workspace_id)

    def validate_fields(self, value):
        return validate_fields(value, require_email=False)

    def validate_theme(self, value):
        if not isinstance(value, dict) or set(value) - {"primary", "background", "text"}:
            raise serializers.ValidationError("Choose a primary, background and text color.")
        if any(
            not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color)
            for color in value.values()
        ):
            raise serializers.ValidationError("Use six-digit hex colors.")

        def luminance(color):
            channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
            return sum(
                v * weight for v, weight in zip(linear, [0.2126, 0.7152, 0.0722], strict=True)
            )

        light, dark = sorted(
            [
                luminance(value.get("background", "#ffffff")),
                luminance(value.get("text", "#0c1b3a")),
            ],
            reverse=True,
        )
        if (light + 0.05) / (dark + 0.05) < 4.5:
            raise serializers.ValidationError(
                "Choose text and background colors with readable contrast."
            )
        return value

    def validate_button_align(self, value):
        if value not in {"left", "center", "right"}:
            raise serializers.ValidationError("Choose left, center or right.")
        return value

    def validate_submission_tags(self, value):
        if (
            not isinstance(value, list)
            or len(value) > 20
            or any(not isinstance(tag, str) or not 1 <= len(tag.strip()) <= 50 for tag in value)
        ):
            raise serializers.ValidationError("Use up to 20 tags of 1–50 characters.")
        return list(dict.fromkeys(tag.strip() for tag in value))

    def validate_redirect_url(self, value):
        if value:
            try:
                URLValidator(schemes=["https"])(value)
            except DjangoValidationError:
                raise serializers.ValidationError(
                    "Use a complete HTTPS redirect address."
                ) from None
        return value

    def validate(self, attrs):
        fields = attrs.get("fields", self.instance.fields if self.instance else [])
        rules = attrs.get("branching", self.instance.branching if self.instance else [])
        validate_fields(
            fields,
            require_email=attrs.get(
                "capture_contacts", self.instance.capture_contacts if self.instance else True
            ),
        )
        validate_branching(rules, fields)
        return attrs


class FormList(generics.ListCreateAPIView):
    serializer_class = FormSerializer
    pagination_class = None

    def get_queryset(self):
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
        return LeadForm.objects.for_workspace(self.kwargs["workspace_id"]).annotate(
            submissions=Count("formsubmission")
        )

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
                    "answers": answer_metadata(
                        json.loads(row.answers),
                        download_prefix=f"/api/workspaces/{workspace_id}/forms/{pk}/submissions/{row.pk}/",
                    ),
                    "consent_text": row.consent_text,
                    "link_id": row.link_id,
                    "action_errors": row.action_errors,
                    "actions": [
                        {
                            "id": job.pk,
                            "operation": job.operation,
                            "status": job.status,
                            "error": json.loads(job.result).get("error", ""),
                            "accepted": json.loads(job.result).get("accepted"),
                        }
                        for job in row.action_jobs
                    ],
                }
                for row in FormSubmission.objects.for_workspace(workspace_id)
                .filter(form=form)
                .prefetch_related(
                    Prefetch(
                        "integrationjob_set",
                        queryset=IntegrationJob.objects.for_workspace(workspace_id),
                        to_attr="action_jobs",
                    )
                )[:500]
            ]
        )


class FormThrottle(AnonRateThrottle):
    rate = "20/min"


class PublicFormView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [FormThrottle]

    def get(self, request, slug):
        form = get_object_or_404(LeadForm.all_objects, slug=slug, published=True, closed=False)
        return Response(
            {
                key: getattr(form, key)
                for key in [
                    "title",
                    "description",
                    "fields",
                    "branching",
                    "theme",
                    "button_align",
                    "consent_text",
                    "success_text",
                ]
            }
        )

    def post(self, request, slug):
        with transaction.atomic():
            form = get_object_or_404(
                LeadForm.all_objects.select_for_update(), slug=slug, published=True, closed=False
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
                return Response(
                    {
                        "received": True,
                        "message": form.success_text,
                        "redirect_url": form.redirect_url,
                    }
                )
            answers = clean_answers(form.fields, form.branching, request.data.get("answers"))
            contact = contact_values(form.fields, answers)
            email = contact["email"]
            lead = (
                Lead.objects.for_workspace(form.workspace_id).filter(email__iexact=email).first()
                if form.capture_contacts and email
                else None
            )
            link = (
                DeepLink.objects.for_workspace(form.workspace_id)
                .filter(code=request.data.get("ref", ""), active=True)
                .first()
                if isinstance(request.data.get("ref", ""), str)
                else None
            )
            if form.capture_contacts and email and not lead:
                from apps.billing.gating import check_within_limit

                check_within_limit(form.workspace_id, "max_contacts")
                lead = Lead.objects.for_workspace(form.workspace_id).create(
                    workspace_id=form.workspace_id,
                    email=email,
                    name=(
                        answers.get("name", "") if isinstance(answers.get("name", ""), str) else ""
                    )[:150],
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
            if lead:
                if contact["name"]:
                    lead.name = contact["name"]
                lead.fields = {**lead.fields, **contact["fields"]}
                lead.save(update_fields=["name", "fields"])
            if lead and form.submission_tags:
                lead.tags = sorted(set(lead.tags) | set(form.submission_tags))
                lead.save(update_fields=["tags"])
            submission = FormSubmission.objects.for_workspace(form.workspace_id).create(
                workspace_id=form.workspace_id,
                form=form,
                lead=lead,
                link=link,
                request_id=request_id,
                answers=json.dumps(answers),
                consent_text=form.consent_text,
            )
            from apps.public_api.services import emit

            from .form_actions import queue_submission_actions

            queue_submission_actions(
                submission, form, lead, {**answers, "email": email, "name": contact["name"]}
            )
            emit(
                form.workspace_id,
                "form.submitted",
                {
                    "form_id": str(form.pk),
                    "submission_id": str(submission.pk),
                    "lead_id": str(lead.pk) if lead else None,
                    "answers": answer_metadata(answers),
                },
            )
            # Existing opt-outs remain opted out; workers recheck before performing any action.
        return Response(
            {"received": True, "message": form.success_text, "redirect_url": form.redirect_url},
            status=201,
        )
