"""Delete the accounts the browser suite creates (`e2e-<timestamp>@example.com`).

Every Playwright run signs up a fresh user and workspace, so without this the local
console fills with "E2E Studio" copies that look like real customers. Only runs with
CHANNEL_ADAPTER_MODE=fake, which production settings refuse to start with, so it
cannot touch a live database.
"""

import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

PATTERN = re.compile(r"^e2e-\d+@example\.com$")


class Command(BaseCommand):
    help = "Remove browser-test users and the workspaces only they belong to."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report without deleting")

    def handle(self, *args, dry_run=False, **options):
        from apps.platform_ops.models import SupportTicket
        from apps.tenants.models import Membership, User, Workspace

        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise CommandError("Refusing to run: CHANNEL_ADAPTER_MODE must be 'fake'.")
        users = [
            user
            for user in User.objects.filter(
                email__istartswith="e2e-", email__iendswith="@example.com"
            )
            if PATTERN.match(user.email.lower())
        ]
        ids = {user.pk for user in users}
        # A workspace goes only when every member is a test user; a real person who was
        # invited into one keeps it.
        workspaces = [
            workspace
            for workspace in Workspace.objects.filter(membership__user_id__in=ids).distinct()
            if set(
                Membership.all_objects.filter(workspace=workspace).values_list("user_id", flat=True)
            )
            <= ids
        ]
        tickets = SupportTicket.objects.filter(reporter_email__in=[user.email for user in users])
        self.stdout.write(
            f"{len(users)} test users, {len(workspaces)} workspaces, {tickets.count()} tickets"
            + (" (dry run)" if dry_run else "")
        )
        if dry_run or not users:
            return
        with transaction.atomic():
            tickets.delete()
            for workspace in workspaces:
                workspace.delete()
            User.objects.filter(pk__in=ids).delete()
        self.stdout.write("deleted")
