from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.platform_ops.models import PlatformRole
from apps.platform_ops.security import record
from apps.tenants.models import User


class Command(BaseCommand):
    help = (
        "Grant the first platform owner to an existing account; MFA enrollment is still mandatory."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")

    @transaction.atomic
    def handle(self, *args, **options):
        if PlatformRole.objects.filter(role="owner", active=True).exists():
            raise CommandError("An owner already exists. Use the audited platform invitation flow.")
        try:
            user = User.objects.select_for_update().get(
                username=options["username"], is_active=True
            )
        except User.DoesNotExist as exc:
            raise CommandError("Create an active user account first.") from exc
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        PlatformRole.objects.update_or_create(user=user, defaults={"role": "owner", "active": True})
        record("bootstrap-command", "staff.owner_bootstrapped", target=str(user.pk))
        self.stdout.write(
            "Owner provisioned. Sign in on the internal host and enroll an authenticator."
        )
