"""Local throughput benchmark across many workspaces.

Seeds N workspaces, each with a test channel and a published keyword flow, then drives
M inbound messages per workspace through the real path: signed-webhook persistence →
webhook processing → automation step → delivery. Every stage is timed in-process.

Numbers are only meaningful on PostgreSQL with CHANNEL_ADAPTER_MODE=fake, and they
measure this machine, not production. Use it to catch regressions between changes,
never as evidence of capacity.
"""

import secrets
import time
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.automations.models import Automation, ConversationState
from apps.automations.services import publish
from apps.automations.tasks import step
from apps.channels.ingress import persist_events
from apps.channels.models import ChannelConnection, Delivery, WebhookEvent
from apps.channels.tasks import process_webhook, send_delivery
from apps.tenants.models import User
from apps.tenants.services import create_workspace

GRAPH = {
    "start": "reply",
    "nodes": [
        {"id": "reply", "data": {"kind": "send_message", "text": "Thanks! You said {{last_text}}"}},
        {"id": "done", "data": {"kind": "end"}},
    ],
    "edges": [{"source": "reply", "target": "done"}],
    "triggers": [{"kind": "dm", "keyword": "price"}],
}


def summarize(name, samples, out):
    if not samples:
        out.write(f"{name:<12} no items")
        return
    ordered = sorted(samples)
    total = sum(ordered)
    p = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))] * 1000  # noqa: E731
    out.write(
        f"{name:<12} {len(ordered):>6} items  {total:6.2f}s  "
        f"{len(ordered) / total if total else 0:8.1f}/s  p50 {p(0.5):6.1f}ms  p95 {p(0.95):6.1f}ms"
    )


class Command(BaseCommand):
    help = "Drive N workspaces × M inbound messages through the full pipeline and report timings."

    def add_arguments(self, parser):
        parser.add_argument("--workspaces", type=int, default=50)
        parser.add_argument("--messages", type=int, default=20)
        parser.add_argument("--keep", action="store_true", help="Leave the seeded data in place")

    def handle(self, *args, **options):
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise CommandError(
                "Set CHANNEL_ADAPTER_MODE=fake; the harness only uses test channels."
            )
        stamp = secrets.token_hex(4)
        user = User.objects.create_user(
            username=f"loadtest-{stamp}",
            email=f"loadtest-{stamp}@example.invalid",
            password=secrets.token_urlsafe(24),
        )
        workspaces = []
        started = time.perf_counter()
        for index in range(options["workspaces"]):
            workspace = create_workspace(user, f"Load test {stamp} {index:02d}")
            ChannelConnection.objects.for_workspace(workspace).create(
                workspace=workspace,
                external_account_id=f"load-{workspace.pk}",
                display_name="Load channel",
                access_token="local-test-token",
                expires_at=timezone.now() + timedelta(days=60),
                is_test=True,
            )
            automation = Automation.objects.for_workspace(workspace).create(
                workspace=workspace, name="Price reply", draft=GRAPH
            )
            publish(automation, GRAPH, user)
            workspaces.append(workspace)
        self.stdout.write(
            f"seeded {len(workspaces)} workspaces in {time.perf_counter() - started:.2f}s"
        )
        ids = [w.pk for w in workspaces]
        timings = {"ingest": [], "webhook": [], "automation": [], "delivery": []}
        # Realtime hints need Redis; the benchmark measures the durable path only.
        with patch("apps.crm.services.notify"):
            for workspace in workspaces:
                for n in range(options["messages"]):
                    t = time.perf_counter()
                    persist_events(
                        "instagram",
                        [
                            (
                                f"load-{workspace.pk}",
                                f"load-{stamp}-{n}",
                                {"sender_id": f"lead-{n}", "text": "price please", "kind": "dm"},
                            )
                        ],
                    )
                    timings["ingest"].append(time.perf_counter() - t)
            for wid, pk in WebhookEvent.all_objects.filter(
                workspace_id__in=ids, status="pending"
            ).values_list("workspace_id", "pk"):
                t = time.perf_counter()
                process_webhook(str(wid), str(pk))
                timings["webhook"].append(time.perf_counter() - t)
            # Two steps per flow: send_message, then end.
            for _ in range(2):
                for wid, pk in ConversationState.all_objects.filter(
                    workspace_id__in=ids, status="running"
                ).values_list("workspace_id", "pk"):
                    t = time.perf_counter()
                    step(str(wid), str(pk))
                    timings["automation"].append(time.perf_counter() - t)
            Delivery.all_objects.filter(workspace_id__in=ids, status="pending").update(
                available_at=timezone.now()
            )
            for wid, pk in Delivery.all_objects.filter(
                workspace_id__in=ids, status="pending"
            ).values_list("workspace_id", "pk"):
                t = time.perf_counter()
                send_delivery(str(wid), str(pk))
                timings["delivery"].append(time.perf_counter() - t)
        for name, samples in timings.items():
            summarize(name, samples, self.stdout)
        sent = Delivery.all_objects.filter(workspace_id__in=ids, status="sent").count()
        expected = options["workspaces"] * options["messages"]
        self.stdout.write(f"delivered {sent}/{expected} replies")
        if not options["keep"]:
            for workspace in workspaces:
                workspace.delete()
            user.delete()
            self.stdout.write("cleaned up")
        if sent != expected:
            raise CommandError("Some messages did not complete the pipeline.")
