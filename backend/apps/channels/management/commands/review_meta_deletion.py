"""Operator review of cases that cannot safely be erased from a Meta identifier alone."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.channels.models import MetaDataDeletion


class Command(BaseCommand):
    help = (
        "List pending Meta requests or record verified manual erasure. Does not itself erase data."
    )

    def add_arguments(self, parser):
        parser.add_argument("code", nargs="?")
        parser.add_argument("--retry", action="store_true")
        parser.add_argument("--confirm-erasure", action="store_true")
        parser.add_argument("--reason", default="")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["code"]:
            for record in MetaDataDeletion.objects.exclude(status="completed").order_by(
                "created_at"
            )[:100]:
                self.stdout.write(
                    f"{record.code} {record.status} {record.error_code} targets={len(record.connection_ids)}"
                )
            return
        record = MetaDataDeletion.objects.select_for_update().filter(code=options["code"]).first()
        if not record:
            raise CommandError("Unknown confirmation code.")
        if record.status == "processing":
            raise CommandError("Wait for the active erasure worker or interrupted-worker review.")
        if record.status == "completed":
            self.stdout.write("Already completed.")
            return
        if options["retry"]:
            if options["confirm_erasure"]:
                raise CommandError("Choose retry or verified completion, not both.")
            record.status, record.error_code = "pending", ""
        else:
            reason = options["reason"].strip()
            if not options["confirm_erasure"] or not 20 <= len(reason) <= 500:
                raise CommandError(
                    "After verifying erasure and any lawful retention, use --confirm-erasure --reason with a 20–500 character internal review reference. Do not include personal data."
                )
            record.status, record.completed_at, record.subject_id = "completed", timezone.now(), ""
            record.error_code, record.resolution_note = "", reason
        record.save()
        self.stdout.write(record.status)
