from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.crm.models import Conversation
from apps.platform_ops.security import pause_guard
from apps.tenants.dispatch import enqueue_once

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
            return
        config = AgentConfig.objects.for_workspace(workspace_id).filter(enabled=True).first()
        if not config or not conversation.ai_enabled or conversation.identity.lead.opted_out:
            run.status = "skipped"
            run.save()
            return
        run.status = "running"
        run.started_at = timezone.now()
        run.save()
    try:
        run_agent(run, config)
    except Exception as exc:
        # Do not retry a partially executed agent automatically. Its checkpoint,
        # tool audit and reserved usage are retained for operator inspection.
        run.status = "needs_review"
        run.error_code = type(exc).__name__[:50]
    else:
        run.status = "complete"
        run.completed_at = timezone.now()
    run.save()


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
        document.status = "processing"
        document.save()
    try:
        ingest(document, config)
    except Exception as exc:
        document.status = "failed"
        document.error_code = type(exc).__name__[:50]
        document.save()
