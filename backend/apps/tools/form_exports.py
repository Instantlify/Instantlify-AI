import csv
import io
import json

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership

from .form_files import answer_metadata
from .models import FormSubmission, LeadForm


def spreadsheet_value(value):
    if isinstance(value, dict):
        value = value.get("name", json.dumps(value))
    elif isinstance(value, list):
        value = ", ".join(value)
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


class SubmissionExportView(APIView):
    def get(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        form = get_object_or_404(LeadForm.objects.for_workspace(workspace_id), pk=pk)
        rows = (
            FormSubmission.objects.for_workspace(workspace_id)
            .filter(form=form)
            .order_by("created_at", "id")
        )
        as_csv = request.query_params.get("file_type") == "csv"

        def records():
            for row in rows.iterator(chunk_size=50):
                yield {
                    "id": str(row.pk),
                    "created_at": row.created_at.isoformat(),
                    "lead_id": str(row.lead_id) if row.lead_id else None,
                    "consent_text": row.consent_text,
                    "answers": answer_metadata(
                        json.loads(row.answers),
                        download_prefix=f"/api/workspaces/{workspace_id}/forms/{pk}/submissions/{row.pk}/",
                    ),
                }

        def chunks():
            if as_csv:
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                ids = [field["id"] for field in form.fields]
                yield "\ufeff"
                writer.writerow(
                    [
                        "Submission",
                        "Submitted at",
                        "Consent",
                        *[spreadsheet_value(field["label"]) for field in form.fields],
                        "All answers (JSON)",
                    ]
                )
                yield buffer.getvalue()
                for row in records():
                    buffer.seek(0)
                    buffer.truncate(0)
                    writer.writerow(
                        [
                            row["id"],
                            row["created_at"],
                            spreadsheet_value(row["consent_text"]),
                            *[spreadsheet_value(row["answers"].get(key, "")) for key in ids],
                            json.dumps(row["answers"]),
                        ]
                    )
                    yield buffer.getvalue()
            else:
                yield "["
                for index, row in enumerate(records()):
                    yield ("," if index else "") + json.dumps(row)
                yield "]"

        extension = "csv" if as_csv else "json"
        response = StreamingHttpResponse(
            chunks(), content_type="text/csv; charset=utf-8" if as_csv else "application/json"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{form.slug}-responses.{extension}"'
        )
        response["Cache-Control"] = "private, no-store"
        return response
