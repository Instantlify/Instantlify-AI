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
    from apps.agents.models import AgentConfig, KnowledgeDocument, ToolCall, UsageRecord
    from apps.analytics.models import Experiment, FunnelEvent
    from apps.automations.models import Automation
    from apps.billing.models import AICreditBalance, AICreditTransaction, Offer, Payment
    from apps.channels.models import ChannelConnection
    from apps.content.models import BioPage, ScheduledPost
    from apps.crm.models import (
        ChannelIdentity,
        Conversation,
        IntegrationConfig,
        IntegrationJob,
        InternalNote,
        Lead,
        Message,
    )
    from apps.marketplace.models import Template, TemplateInstall, TemplatePurchase
    from apps.public_api.models import APIKey, MCPClient, WebhookSubscription
    from apps.tools.models import DeepLink, ShieldEvent, ShieldRule, WebChatSettings

    from .models import AuditEvent, Membership, WorkspaceBranding

    return {
        "deeplinks": (
            DeepLink,
            ["id", "title", "platform", "target", "code", "clicks", "active", "created_at"],
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
        "messages": (
            Message,
            ["id", "conversation_id", "direction", "text", "kind", "created_at"],
        ),
        "notes": (InternalNote, ["id", "conversation_id", "author_id", "text", "created_at"]),
        "automations": (
            Automation,
            ["id", "name", "draft", "published", "revision", "enabled"],
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
                "handoff_keywords",
            ],
        ),
        "knowledge": (KnowledgeDocument, ["id", "title", "source", "file_type"]),
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
            ["id", "integration_id", "operation", "status", "created_at"],
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
    from apps.billing.models import BillingEvent, Payment
    from apps.channels.models import Delivery, WebhookEvent
    from apps.crm.models import IntegrationJob, InternalNote, Message
    from apps.marketplace.models import TemplatePurchase
    from apps.public_api.models import OutboundWebhook

    open_work = ["pending", "sending", "executing", "processing"]
    return [
        (WebhookEvent, {"payload": "{}"}, open_work),
        (Delivery, {"payload": "{}"}, open_work),
        (ToolCall, {"input": "{}", "output": "{}"}, open_work),
        (AgentRun, {"checkpoint": "{}"}, ["pending", "running"]),
        (Message, {"text": "", "attachments": "[]"}, []),
        (InternalNote, {"text": ""}, []),
        (IntegrationJob, {"payload": "{}", "result": "{}"}, open_work),
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

    cutoff = timezone.now() - timedelta(days=settings.RETENTION_DAYS)
    for model, blanks, skip_statuses in retention_policy():
        rows = model.all_objects.filter(created_at__lt=cutoff)
        if skip_statuses:
            rows = rows.exclude(status__in=skip_statuses)
        rows.update(**blanks)
    VoiceAsset.all_objects.filter(created_at__lt=timezone.now() - timedelta(hours=2)).delete()
    OAuthState.all_objects.filter(expires_at__lt=timezone.now() - timedelta(days=1)).delete()
    DataOperation.all_objects.filter(
        created_at__lt=timezone.now() - timedelta(days=1), kind="export"
    ).delete()
