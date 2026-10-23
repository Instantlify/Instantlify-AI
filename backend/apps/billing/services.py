from decimal import Decimal

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from apps.agents.models import UsageRecord
from apps.tenants.models import Workspace

from .models import BillingAccount


def payments_url(workspace_id, query=""):
    """Where someone lands when Stripe sends them back.

    Their own Settings > Subscription tab, never PUBLIC_APP_URL: that is the anonymous
    marketing page, which offers "Sign in" and "Get started" whatever the session says.
    Someone who has just paid reads that as having been signed out.
    """
    extra = f"&{query.lstrip('?')}" if query else ""
    return f"{settings.PUBLIC_APP_URL}/w/{workspace_id}/settings?tab=subscription{extra}"


def return_url(job, query=""):
    """Stripe return for a billing job: the signup wizard while someone is still
    choosing their first plan, otherwise the Subscription tab."""
    if job.return_to == "onboarding":
        extra = f"?{query.lstrip('?')}" if query else ""
        return f"{settings.PUBLIC_APP_URL}/onboarding/{extra}"
    return payments_url(job.workspace_id, query)


def account_for(workspace_id):
    from .reseller import effective_billing_workspace_id

    target_id = effective_billing_workspace_id(workspace_id)
    return BillingAccount.objects.for_workspace(target_id).get_or_create(workspace_id=target_id)[0]


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
    cap = account.usage_limit
    if kind == "generation" and cap is not None and used >= cap:
        raise PermissionDenied("The AI message limit has been reached.")
    if config.billing_mode == "platform_credits" and not config.is_test:
        from .credits import ensure_credit

        if not ensure_credit(config.workspace_id):
            raise PermissionDenied("credits_exhausted")
    return UsageRecord.objects.for_workspace(config.workspace_id).create(
        workspace_id=config.workspace_id,
        key=key,
        provider=config.provider,
        model=config.model,
        kind=kind,
        billing_mode=config.billing_mode,
    )


def complete_usage(record, completion, config):
    """One record per turn, one credit ledger row per model call. BYO workspaces are
    costed from their own configured prices and never debited."""
    record.calls += 1
    record.input_tokens += completion.input_tokens
    record.output_tokens += completion.output_tokens
    if config.billing_mode == "platform_credits" and not config.is_test:
        from .credits import charge

        # After a provider fallback the answering model differs from the configured one;
        # charge the rate of the model that actually did the work.
        answered = getattr(completion, "model", "")
        row = charge(
            config.workspace_id,
            key=f"usage:{record.id}:{record.calls}",
            model=answered if isinstance(answered, str) and answered else config.model,
            tokens_in=completion.input_tokens,
            tokens_out=completion.output_tokens,
            description=f"{record.kind} call {record.calls}",
            usage_record=record,
        )
        record.cost += -row.amount_cents / Decimal(100)
    else:
        record.cost = (
            Decimal(record.input_tokens) * config.input_cost_per_million
            + Decimal(record.output_tokens) * config.output_cost_per_million
        ) / Decimal(1000000)
    record.status = "complete"
    record.save()


def charge_embedding(config, record, tokens):
    """Embeddings are input-only usage; debited like any other call on prepaid credits."""
    if config.billing_mode != "platform_credits" or config.is_test or not tokens:
        return
    from .credits import charge

    row = charge(
        config.workspace_id,
        key=f"usage:{record.id}:embed",
        model=config.embedding_model,
        tokens_in=tokens,
        description=f"{record.kind} ({tokens} tokens)",
        usage_record=record,
    )
    UsageRecord.objects.for_workspace(config.workspace_id).filter(pk=record.pk).update(
        cost=-row.amount_cents / Decimal(100), billing_mode=config.billing_mode
    )


def charge_transcription(config, record, seconds):
    """Speech-to-text is billed per second of audio. The rate card holds it like any
    model, in cents per million units, where a unit is one second (whisper-1 at
    $0.006/min is 10,000 cents per million seconds). Prepaid workspaces are debited;
    BYO-key workspaces get the provider's real cost recorded, since the charge lands on
    their own OpenAI bill."""
    import math

    from apps.agents.voice import TRANSCRIPTION_MODEL

    from .credits import charge, price, resolve_rate

    billed = math.ceil(seconds) if seconds > 0 else 0
    fields = {
        "model": TRANSCRIPTION_MODEL,
        "audio_seconds": Decimal(str(round(seconds, 2))),
        "billing_mode": config.billing_mode,
        "status": "complete",
    }
    if billed and config.billing_mode == "platform_credits" and not config.is_test:
        row = charge(
            config.workspace_id,
            key=f"usage:{record.id}:transcribe",
            model=TRANSCRIPTION_MODEL,
            tokens_in=billed,
            description=f"transcription ({billed} s audio)",
            usage_record=record,
        )
        fields["cost"] = -row.amount_cents / Decimal(100)
    elif billed and not config.is_test:
        _, real = price(resolve_rate(TRANSCRIPTION_MODEL), tokens_in=billed)
        fields["cost"] = real / Decimal(100)
    UsageRecord.objects.for_workspace(config.workspace_id).filter(pk=record.pk).update(**fields)
