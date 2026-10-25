from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.crm.models import Conversation
from apps.platform_ops.security import pause_guard
from apps.tenants.dispatch import enqueue_once, release

from .models import AgentConfig, AgentRun, KnowledgeDocument


@shared_task(ignore_result=True)
def dispatch_agents():
    for model, task in [(AgentRun, process_run), (KnowledgeDocument, ingest_document)]:
        for wid, pk in model.all_objects.filter(status="pending").values_list("workspace_id", "pk")[
            :50
        ]:
            enqueue_once(task, wid, pk)
    AgentRun.all_objects.filter(
        status="running", started_at__lt=timezone.now() - timedelta(minutes=5)
    ).update(status="needs_review", error_code="worker_interrupted")


@shared_task(ignore_result=True, soft_time_limit=100, time_limit=120)
@pause_guard("ai")
def process_run(workspace_id, run_id):
    from .runtime import run_agent
    from .simple import run_simple

    with transaction.atomic():
        run = (
            AgentRun.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=run_id, status="pending")
            .first()
        )
        if not run:
            return
        conversation = (
            Conversation.objects.for_workspace(workspace_id)
            .select_for_update()
            .get(pk=run.message.conversation_id)
        )
        if (
            AgentRun.objects.for_workspace(workspace_id)
            .filter(message__conversation=conversation, status="running")
            .exists()
        ):
            # Deferred behind the conversation's current run: stay eligible for the
            # next tick rather than waiting out the dispatch marker.
            release(process_run, run_id)
            return
        config = AgentConfig.objects.for_workspace(workspace_id).filter(enabled=True).first()
        if not config or not conversation.ai_enabled or conversation.identity.lead.opted_out:
            run.status = "skipped"
            run.save()
            return
        from apps.billing.gating import guard

        if not guard(workspace_id, "ai_agent_enabled"):
            # Plan no longer includes the agent: fail visibly, never drop the lead's message.
            run.status = "skipped"
            run.error_code = "plan_limit"
            run.save()
            return
        if config.billing_mode == "platform_credits" and not config.is_test:
            from apps.billing.credits import ensure_credit

            if not ensure_credit(workspace_id):
                park_for_payment(run, config)
                return
        run.status = "running"
        run.started_at = timezone.now()
        run.save()
    try:
        (run_simple if config.mode == "simple" else run_agent)(run, config)
    except PermissionDenied as exc:
        if "credits_exhausted" in str(exc.detail):
            park_for_payment(run, config)
            return
        run.status = "needs_review"
        run.error_code = "PermissionDenied"
    except Exception as exc:
        # Do not retry a partially executed agent automatically. Its checkpoint,
        # tool audit and reserved usage are retained for operator inspection.
        run.status = "needs_review"
        run.error_code = type(exc).__name__[:50]
    else:
        run.status = "complete"
        run.completed_at = timezone.now()
    run.save()


def park_for_payment(run, config):
    """The lead's message waits, visibly, until the workspace buys credits."""
    from apps.crm.services import notify
    from apps.tenants.services import audit

    run.status = "needs_payment"
    run.error_code = "credits_exhausted"
    run.save()
    audit(run.workspace, None, "ai.credits_exhausted", run.id)
    notify(run.workspace_id)
    from django.db import transaction as _transaction

    from apps.billing.credits import balance_for
    from apps.billing.emails import credits_low

    balance = balance_for(run.workspace_id).balance_cents
    _transaction.on_commit(lambda: credits_low(run.workspace_id, balance))


@shared_task(ignore_result=True, soft_time_limit=100, time_limit=120)
@pause_guard("ai")
def ingest_document(workspace_id, document_id):
    from .rag import ingest

    with transaction.atomic():
        document = (
            KnowledgeDocument.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=document_id, status="pending")
            .first()
        )
        if not document:
            return
        config = AgentConfig.objects.for_workspace(workspace_id).first()
        if not config:
            document.status = "failed"
            document.error_code = "agent_not_configured"
            document.save()
            return
        from apps.billing.gating import guard

        if not guard(workspace_id, "ai_agent_enabled"):
            document.status, document.error_code = "failed", "plan_limit"
            document.save()
            return
        document.status = "processing"
        document.save()
    try:
        ingest(document, config)
    except Exception as exc:
        document.status = "failed"
        document.error_code = type(exc).__name__[:50]
        document.save()
