import json
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from .dispatch import enqueue_once
from .models import DataOperation, Workspace


@shared_task(ignore_result=True)
def dispatch_data_operations():
    for wid, pk in DataOperation.all_objects.filter(status="pending").values_list(
        "workspace_id", "pk"
    )[:10]:
        enqueue_once(process_data_operation, wid, pk, ttl=150)


@shared_task(ignore_result=True, soft_time_limit=100, time_limit=120)
def process_data_operation(workspace_id, operation_id):
    try:
        run_data_operation(workspace_id, operation_id)
    except Exception as exc:
        # The work rolled back; fail visibly instead of re-running a heavy export forever.
        DataOperation.objects.for_workspace(workspace_id).filter(
            pk=operation_id, status="pending"
        ).update(status="failed", error_code=type(exc).__name__[:50])
        logging.getLogger(__name__).warning(
            "Data operation failed", extra={"event_code": "data_operation_failed"}
        )


def export_tables():
    """Every customer-bearing table, with credentials, hashes and provider tokens omitted.
    Adding a model that stores tenant data means adding it here (see the export test)."""
    from apps.agents.models import (
        AgentConfig,
        KnowledgeBase,
        KnowledgeDocument,
        KnowledgeSourceSync,
        ToolCall,
        UsageRecord,
    )
    from apps.analytics.models import Experiment, FunnelEvent
    from apps.automations.models import (
        Automation,
        AutomationExecution,
        WorkflowActionJob,
        WorkflowLink,
    )
    from apps.billing.models import AICreditBalance, AICreditTransaction, Offer, Payment
    from apps.channels.models import ChannelConnection
    from apps.content.models import BioPage, ScheduledPost
    from apps.crm.models import (
        AssignmentNotification,
        Campaign,
        CampaignRecipient,
        ChannelIdentity,
        ContactSegment,
        Conversation,
        ConversationRead,
        IntegrationConfig,
        IntegrationJob,
        InternalNote,
        Lead,
        Message,
        MessageAttachment,
        SavedReply,
    )
    from apps.marketplace.models import Template, TemplateInstall, TemplatePurchase
    from apps.public_api.models import APIKey, MCPClient, WebhookSubscription
    from apps.tools.models import (
        CreatorKit,
        DeepLink,
        FormSubmission,
        LeadForm,
        LinkClickDay,
        ShieldEvent,
        ShieldRule,
        WebChatSettings,
    )

    from .models import AuditEvent, Membership, WorkspaceBranding

    return {
        "deeplinks": (
            DeepLink,
            [
                "id",
                "title",
                "platform",
                "open_external",
                "target",
                "code",
                "clicks",
                "active",
                "created_at",
                "campaign",
                "source",
                "medium",
            ],
        ),
        "link_click_days": (LinkClickDay, ["id", "link_id", "day", "clicks"]),
        "forms": (
            LeadForm,
            [
                "id",
                "title",
                "slug",
                "description",
                "fields",
                "submission_actions",
                "automation_id",
                "branching",
                "theme",
                "redirect_url",
                "submission_tags",
                "button_align",
                "closed",
                "capture_contacts",
                "consent_text",
                "success_text",
                "published",
                "created_at",
            ],
        ),
        "form_submissions": (
            FormSubmission,
            [
                "id",
                "form_id",
                "lead_id",
                "link_id",
                "answers",
                "consent_text",
                "action_errors",
                "workflow_state",
                "workflow_status",
                "workflow_due_at",
                "created_at",
            ],
        ),
        "creator_kit": (
            CreatorKit,
            [
                "id",
                "slug",
                "name",
                "headline",
                "bio",
                "contact_email",
                "links",
                "statistics",
                "live_connection_ids",
                "live_insights",
                "live_stats_checked_at",
                "live_stats_next_at",
                "live_stats_error",
                "services",
                "published",
            ],
        ),
        "shield_rules": (ShieldRule, ["id", "name", "keywords", "action", "enabled", "created_at"]),
        "shield_events": (
            ShieldEvent,
            ["id", "rule_name", "comment_id", "author", "text", "action_taken", "created_at"],
        ),
        "webchat": (
            WebChatSettings,
            ["title", "greeting", "color", "bot_enabled", "allowed_domains", "updated_at"],
        ),
        "members": (Membership, ["id", "user_id", "user__email", "role", "created_at"]),
        "branding": (
            WorkspaceBranding,
            ["brand_name", "logo_url", "primary_color", "support_email", "custom_domain"],
        ),
        "connections": (
            ChannelConnection,
            ["id", "provider", "external_account_id", "display_name", "status", "created_at"],
        ),
        "leads": (
            Lead,
            [
                "id",
                "name",
                "handle",
                "avatar_url",
                "email",
                "stage",
                "tags",
                "fields",
                "opted_out",
                "created_at",
            ],
        ),
        "identities": (ChannelIdentity, ["id", "lead_id", "connection_id", "external_id"]),
        "conversations": (
            Conversation,
            ["id", "identity_id", "assigned_to_id", "status", "ai_enabled", "created_at"],
        ),
        "campaigns": (
            Campaign,
            [
                "id",
                "name",
                "connection_id",
                "text",
                "buttons",
                "media_url",
                "media_type",
                "tag",
                "audience",
                "status",
                "scheduled_at",
                "launched_at",
                "finished_at",
                "expected_count",
                "created_at",
            ],
        ),
        "campaign_recipients": (
            CampaignRecipient,
            [
                "id",
                "campaign_id",
                "conversation_id",
                "lead_id",
                "text_delivery_id",
                "media_delivery_id",
                "status",
                "error_code",
                "created_at",
            ],
        ),
        "messages": (
            Message,
            ["id", "conversation_id", "direction", "text", "kind", "created_at", "sequence"],
        ),
        "notes": (InternalNote, ["id", "conversation_id", "author_id", "text", "created_at"]),
        # File bytes stay out of the export; the record shows what was sent and when.
        "message_attachments": (
            MessageAttachment,
            ["id", "conversation_id", "filename", "content_type", "size", "created_at"],
        ),
        "saved_replies": (SavedReply, ["id", "text", "position", "created_at"]),
        "conversation_reads": (ConversationRead, ["id", "conversation_id", "user_id", "read_at"]),
        "assignment_notifications": (
            AssignmentNotification,
            ["id", "recipient_id", "actor_id", "lead_id", "read_at", "created_at"],
        ),
        "automations": (
            Automation,
            ["id", "name", "draft", "published", "revision", "enabled"],
        ),
        "automation_executions": (
            AutomationExecution,
            [
                "id",
                "conversation_id",
                "automation_id",
                "automation_name",
                "revision",
                "status",
                "steps",
                "node_id",
                "error_code",
                "trace",
                "created_at",
                "finished_at",
            ],
        ),
        "workflow_actions": (
            WorkflowActionJob,
            ["id", "state_id", "kind", "status", "error_code", "created_at"],
        ),
        "workflow_links": (
            WorkflowLink,
            [
                "id",
                "conversation_id",
                "source_node",
                "target",
                "automation_id",
                "clicked_at",
                "created_at",
            ],
        ),
        "experiments": (
            Experiment,
            ["id", "name", "control_id", "variant_id", "split", "goal", "status", "winner"],
        ),
        "funnel_events": (
            FunnelEvent,
            [
                "id",
                "kind",
                "provider",
                "lead_id",
                "conversation_id",
                "automation_id",
                "amount_cents",
                "created_at",
            ],
        ),
        "contact_segments": (ContactSegment, ["id", "name", "prompt", "enabled", "updated_at"]),
        "agent": (
            AgentConfig,
            [
                "name",
                "system_prompt",
                "provider",
                "model",
                "allowed_tools",
                "enabled",
                "qualifying_fields",
                "segmentation_enabled",
                "segmentation_prompt",
                "handoff_keywords",
            ],
        ),
        "knowledge": (
            KnowledgeDocument,
            ["id", "title", "source", "file_type", "source_revision", "knowledge_base_id"],
        ),
        "knowledge_bases": (KnowledgeBase, ["id", "name", "description", "created_at"]),
        "knowledge_syncs": (
            KnowledgeSourceSync,
            [
                "id",
                "integration_id",
                "enabled",
                "interval_minutes",
                "status",
                "next_run_at",
                "last_checked_at",
                "last_success_at",
                "error_code",
            ],
        ),
        "tool_calls": (ToolCall, ["id", "run_id", "name", "status", "created_at"]),
        "usage": (
            UsageRecord,
            ["id", "model", "kind", "input_tokens", "output_tokens", "cost", "created_at"],
        ),
        "integrations": (
            IntegrationConfig,
            ["id", "provider", "options", "enabled", "is_test", "status"],
        ),
        "integration_jobs": (
            IntegrationJob,
            ["id", "integration_id", "form_submission_id", "operation", "status", "created_at"],
        ),
        "ai_credit_balance": (
            AICreditBalance,
            [
                "balance_cents",
                "auto_topup_enabled",
                "auto_topup_threshold_cents",
                "auto_topup_amount_cents",
            ],
        ),
        "ai_credit_transactions": (
            AICreditTransaction,
            [
                "id",
                "type",
                "status",
                "amount_cents",
                "real_cost_cents",
                "remaining_balance_cents",
                "model",
                "tokens_in",
                "tokens_out",
                "description",
                "created_at",
            ],
        ),
        "offers": (Offer, ["id", "name", "description", "amount_cents", "currency", "active"]),
        "payments": (
            Payment,
            [
                "id",
                "offer_id",
                "conversation_id",
                "lead_id",
                "amount_cents",
                "currency",
                "status",
                "paid_at",
                "created_at",
            ],
        ),
        "posts": (
            ScheduledPost,
            [
                "id",
                "connection_id",
                "caption",
                "media_url",
                "media_type",
                "scheduled_at",
                "status",
                "provider_post_id",
                "published_at",
            ],
        ),
        "bio_page": (
            BioPage,
            ["slug", "title", "bio", "avatar_url", "accent", "links", "published"],
        ),
        "templates": (
            Template,
            [
                "id",
                "title",
                "slug",
                "description",
                "category",
                "graph",
                "price_cents",
                "status",
                "install_count",
            ],
        ),
        "template_installs": (
            TemplateInstall,
            ["id", "template_id", "automation_id", "created_at"],
        ),
        "template_purchases": (
            TemplatePurchase,
            [
                "id",
                "template_id",
                "title",
                "amount_cents",
                "currency",
                "status",
                "paid_at",
                "created_at",
            ],
        ),
        "api_keys": (
            APIKey,
            ["id", "name", "prefix", "scopes", "created_at", "last_used_at", "revoked_at"],
        ),
        # Which MCP clients (Claude Desktop, agents) used this workspace's keys.
        "mcp_clients": (
            MCPClient,
            [
                "id",
                "api_key_id",
                "client_name",
                "client_version",
                "protocol_version",
                "last_active_at",
                "created_at",
            ],
        ),
        "webhook_subscriptions": (
            WebhookSubscription,
            ["id", "url", "events", "active", "created_at"],
        ),
        "audit": (
            AuditEvent,
            ["id", "action", "actor_id", "target_id", "metadata", "created_at"],
        ),
    }


def run_data_operation(workspace_id, operation_id):
    from apps.billing.models import BillingAccount
    from apps.crm.models import IntegrationConfig

    with transaction.atomic():
        job = (
            DataOperation.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=operation_id, status="pending")
            .first()
        )
        if not job:
            return
        if job.kind == "delete":
            account = BillingAccount.objects.for_workspace(workspace_id).first()
            if (
                account
                and account.subscription_id
                and account.status not in {"canceled", "incomplete_expired"}
            ):
                job.status = "failed"
                job.error_code = "cancel_subscription_first"
                job.save()
                return
            Workspace.objects.get(pk=workspace_id).delete()
            return
        result = {
            name: list(model.objects.for_workspace(workspace_id).values(*fields).iterator())
            for name, (model, fields) in export_tables().items()
        }
        # Deleting local rows is not deletion in third-party systems. The manifest tells
        # the owner which external systems also hold copies of their data.
        result["manifest"] = {
            "workspace_id": str(workspace_id),
            "exported_at": timezone.now().isoformat(),
            "retention_days": settings.RETENTION_DAYS,
            "external_systems": sorted(
                IntegrationConfig.objects.for_workspace(workspace_id)
                .filter(is_test=False)
                .values_list("provider", flat=True)
            ),
        }
        job.result = json.dumps(result, cls=DjangoJSONEncoder)
        job.status = "complete"
        job.save()


def retention_policy():
    """Payload stores scrubbed after RETENTION_DAYS. Rows stay as dedupe/audit tombstones;
    only the customer-bearing field is blanked. Pending work is never scrubbed."""
    from apps.agents.models import AgentRun, ToolCall
    from apps.automations.models import IntentMatch, WorkflowActionJob
    from apps.billing.models import BillingEvent, Payment
    from apps.channels.models import Delivery, WebhookEvent
    from apps.crm.models import IntegrationJob, InternalNote, Message
    from apps.marketplace.models import TemplatePurchase
    from apps.platform_ops.models import CommunityPost, CommunityReply
    from apps.public_api.models import OutboundWebhook
    from apps.tools.models import FormSubmission

    open_work = ["pending", "sending", "executing", "processing"]
    return [
        (WebhookEvent, {"payload": "{}"}, open_work),
        (Delivery, {"payload": "{}"}, open_work),
        (ToolCall, {"input": "{}", "output": "{}"}, open_work),
        (AgentRun, {"checkpoint": "{}"}, ["pending", "running"]),
        (IntentMatch, {"payload": {}}, ["pending", "executing"]),
        (Message, {"text": "", "attachments": "[]"}, []),
        (InternalNote, {"text": ""}, []),
        (IntegrationJob, {"payload": "{}", "result": "{}"}, open_work),
        (
            WorkflowActionJob,
            {"payload": "{}", "result": "{}"},
            [*open_work, "rendering", "polling"],
        ),
        (
            FormSubmission,
            {
                "answers": "{}",
                "workflow_state": "{}",
                "workflow_status": "stopped",
                "workflow_due_at": None,
            },
            [],
        ),
        (CommunityPost, {"body": "[Removed by retention policy]"}, []),
        (CommunityReply, {"body": "[Removed by retention policy]"}, []),
        (OutboundWebhook, {"payload": "{}"}, open_work),
        (BillingEvent, {"payload": "{}"}, open_work),
        # Checkout links expire long before retention; drop them rather than keep dead URLs.
        (Payment, {"checkout_url": ""}, []),
        (TemplatePurchase, {"checkout_url": ""}, []),
    ]


@shared_task(ignore_result=True)
def apply_retention():
    from apps.agents.models import VoiceAsset
    from apps.channels.models import OAuthState
    from apps.crm.models import MessageAttachment

    cutoff = timezone.now() - timedelta(days=settings.RETENTION_DAYS)
    for model, blanks, skip_statuses in retention_policy():
        manager = model.all_objects if hasattr(model, "all_objects") else model.objects
        rows = manager.filter(created_at__lt=cutoff)
        if skip_statuses:
            rows = rows.exclude(status__in=skip_statuses)
        rows.update(**blanks)
    VoiceAsset.all_objects.filter(created_at__lt=timezone.now() - timedelta(hours=2)).delete()
    # Inbox file bytes follow the same retention window as message text.
    MessageAttachment.all_objects.filter(created_at__lt=cutoff).delete()
    OAuthState.all_objects.filter(expires_at__lt=timezone.now() - timedelta(days=1)).delete()
    DataOperation.all_objects.filter(
        created_at__lt=timezone.now() - timedelta(days=1), kind="export"
    ).delete()
