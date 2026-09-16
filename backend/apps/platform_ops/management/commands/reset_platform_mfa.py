from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.platform_ops.models import PlatformRole
from apps.platform_ops.security import record


class Command(BaseCommand):
    help = (
        "Audited server-side recovery: invalidate platform sessions and require new MFA enrollment."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--reason", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        reason = options["reason"].strip()
        if not reason:
            raise CommandError("A recovery reason is required.")
        try:
            role = PlatformRole.objects.select_for_update().get(user__username=options["username"])
        except PlatformRole.DoesNotExist as exc:
            raise CommandError("Platform account not found.") from exc
        role.otp_secret = ""
        role.otp_confirmed = False
        role.version += 1
        role.last_counter = -1
        role.failed_attempts = 0
        role.locked_until = None
        role.save()
        record("recovery-command", "staff.mfa_reset", target=str(role.user_id), reason=reason[:300])
        self.stdout.write(
            "Platform sessions invalidated. Password verification and MFA enrollment are required."
        )
