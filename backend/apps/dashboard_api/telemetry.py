"""Overview telemetry: daily inbound volume per Meta channel, contacts captured, the
share of conversations the AI answered, and a per-channel performance matrix. Every
number is counted from rows the services wrote, never estimated."""

from datetime import datetime, time, timedelta
from statistics import median

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.analytics.models import FunnelEvent
from apps.automations.models import Automation
from apps.crm.models import Lead, Message

META = ("instagram", "messenger", "whatsapp")
INBOUND_KINDS = ("dm", "comment")
# Response-time pairs are computed in Python; cap the rows read per request.
MAX_TIMING_ROWS = 20000


def telemetry(workspace_id, days=14):
    today = timezone.localdate()
    first = today - timedelta(days=days - 1)
    since = timezone.make_aware(datetime.combine(first, time.min))
    dates = [first + timedelta(days=offset) for offset in range(days)]
    daily = {day: {"date": day.isoformat(), "contacts": 0, "other": 0} for day in dates}
    for row in daily.values():
        row.update({provider: 0 for provider in META})

    inbound = FunnelEvent.objects.for_workspace(workspace_id).filter(
        created_at__gte=since, kind__in=INBOUND_KINDS
    )
    for row in (
        inbound.annotate(day=TruncDate("created_at"))
        .values("day", "provider")
        .annotate(total=Count("id"))
    ):
        if row["day"] in daily:
            key = row["provider"] if row["provider"] in META else "other"
            daily[row["day"]][key] += row["total"]
    for row in (
        Lead.objects.for_workspace(workspace_id)
        .filter(created_at__gte=since)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
    ):
        if row["day"] in daily:
            daily[row["day"]]["contacts"] = row["total"]

    conversations = set(
        inbound.exclude(conversation_id=None).values_list("conversation_id", flat=True)
    )
    answered = set(
        Message.objects.for_workspace(workspace_id)
        .filter(
            direction="outbound",
            created_at__gte=since,
            delivery__idempotency_key__startswith="agent-reply:",
        )
        .values_list("conversation_id", flat=True)
    )
    ai_rate = (
        round(len(conversations & answered) / len(conversations), 4) if conversations else None
    )

    channels = {
        row["provider"]: {
            "provider": row["provider"],
            "inbound": row["total"],
            "conversations": row["threads"],
            "median_response_minutes": None,
            "top_automation": None,
        }
        for row in inbound.exclude(provider="")
        .values("provider")
        .annotate(total=Count("id"), threads=Count("conversation_id", distinct=True))
    }
    waits = {}
    pending = {}
    for conversation_id, direction, created_at, provider in (
        Message.objects.for_workspace(workspace_id)
        .filter(created_at__gte=since)
        .order_by("conversation_id", "created_at", "id")
        .values_list(
            "conversation_id",
            "direction",
            "created_at",
            "conversation__identity__connection__provider",
        )[:MAX_TIMING_ROWS]
    ):
        # A customer turn starts at its first unanswered inbound message and ends at the
        # next outbound message of any author.
        if direction == "inbound":
            pending.setdefault(conversation_id, created_at)
        elif conversation_id in pending:
            minutes = (created_at - pending.pop(conversation_id)).total_seconds() / 60
            waits.setdefault(provider, []).append(minutes)
    for provider, values in waits.items():
        if provider in channels:
            channels[provider]["median_response_minutes"] = round(median(values), 1)

    top = {}
    for row in (
        FunnelEvent.objects.for_workspace(workspace_id)
        .filter(created_at__gte=since, kind="triggered")
        .exclude(automation_id=None)
        .values("provider", "automation_id")
        .annotate(runs=Count("id"))
        .order_by("-runs")
    ):
        top.setdefault(row["provider"], row)
    names = dict(
        Automation.objects.for_workspace(workspace_id)
        .filter(pk__in={row["automation_id"] for row in top.values()})
        .values_list("pk", "name")
    )
    for provider, row in top.items():
        if provider in channels and row["automation_id"] in names:
            channels[provider]["top_automation"] = {
                "name": names[row["automation_id"]],
                "runs": row["runs"],
            }

    series = [daily[day] for day in dates]
    return {
        "since": first.isoformat(),
        "days": series,
        "totals": {
            "inbound": sum(sum(row[key] for key in (*META, "other")) for row in series),
            "contacts": sum(row["contacts"] for row in series),
            "conversations": len(conversations),
            "ai_rate": ai_rate,
        },
        "channels": sorted(channels.values(), key=lambda row: -row["inbound"]),
    }
