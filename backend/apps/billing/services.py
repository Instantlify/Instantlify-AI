from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from apps.agents.models import UsageRecord
from apps.tenants.models import Workspace

from .models import BillingAccount


def account_for(workspace_id):
    return BillingAccount.objects.for_workspace(workspace_id).get_or_create(
        workspace_id=workspace_id
    )[0]


@transaction.atomic
def reserve_usage(config, key, kind="generation"):
    """Only customer-facing generations count toward the plan cap and Stripe meter;
    other kinds (transcription, segmentation) are still logged with token counts."""
    Workspace.objects.select_for_update().get(pk=config.workspace_id)
    account = account_for(config.workspace_id)
    existing = UsageRecord.objects.for_workspace(config.workspace_id).filter(key=key).first()
    if existing:
        return existing
    if account.status not in {"active", "trialing"}:
        raise PermissionDenied("AI is paused until billing is active.")
    used = (
        UsageRecord.objects.for_workspace(config.workspace_id)
        .filter(kind="generation", created_at__gte=account.period_start)
        .count()
    )
    if kind == "generation" and used >= account.usage_limit:
        raise PermissionDenied("The AI message limit has been reached.")
    return UsageRecord.objects.for_workspace(config.workspace_id).create(
        workspace_id=config.workspace_id,
        key=key,
        provider=config.provider,
        model=config.model,
        kind=kind,
    )


def complete_usage(record, completion, config):
    """Accumulates: a multi-round agent turn adds every model call to one record."""
    record.input_tokens += completion.input_tokens
    record.output_tokens += completion.output_tokens
    record.cost = (
        Decimal(record.input_tokens) * config.input_cost_per_million
        + Decimal(record.output_tokens) * config.output_cost_per_million
    ) / Decimal(1000000)
    record.status = "complete"
    record.save()
