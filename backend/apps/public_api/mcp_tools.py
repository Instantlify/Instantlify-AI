"""Workspace-management MCP tools: automations, contacts, pipeline, tracking links and
knowledge. None of them message a customer; they change only the workspace's own data,
under the API key's scopes, and every write is audited by the MCP view."""

import uuid

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from rest_framework import serializers

from .mcp import ToolError, _schema

UUID = {"type": "string", "format": "uuid"}


def _id(value, field):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        raise ToolError(f"{field} must be a UUID.") from None


def _limit(args, default, maximum):
    value = args.get("limit", default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ToolError(f"limit must be 1–{maximum}.")
    return value


def _message(exc):
    detail = exc.detail
    if isinstance(detail, dict):
        detail = next(iter(detail.values()))
    if isinstance(detail, list):
        detail = detail[0]
    return str(detail)


def list_automations(workspace_id, args):
    from apps.automations.models import Automation, AutomationExecution

    limit = _limit(args, 50, 100)
    automations = list(
        Automation.objects.for_workspace(workspace_id).order_by("-updated_at")[:limit]
    )
    runs = dict(
        AutomationExecution.objects.for_workspace(workspace_id)
        .filter(automation_id__in=[a.pk for a in automations])
        .values_list("automation_id")
        .annotate(n=Count("id"))
    )
    return {
        "automations": [
            {
                "id": str(a.pk),
                "name": a.name,
                "enabled": a.enabled,
                "published": bool(a.published),
                "revision": a.revision,
                "folder": a.folder,
                "triggers": [
                    {
                        "kind": t.get("kind"),
                        "match": t.get("match", "keyword"),
                        "keyword": t.get("keyword"),
                        "channel": t.get("channel") or "any",
                    }
                    for t in (a.published or a.draft or {}).get("triggers", [])
                ],
                "runs": runs.get(a.pk, 0),
                "updated_at": a.updated_at,
            }
            for a in automations
        ]
    }


def set_automation_enabled(workspace_id, args):
    from apps.automations.models import Automation

    if not isinstance(args.get("enabled"), bool):
        raise ToolError("enabled must be true or false.")
    automation = (
        Automation.objects.for_workspace(workspace_id)
        .filter(pk=_id(args.get("automation_id"), "automation_id"))
        .first()
    )
    if not automation:
        raise ToolError("No automation with that ID in this workspace.")
    if args["enabled"] and not automation.published:
        raise ToolError("Publish the automation in Instantlify before turning it on.")
    automation.enabled = args["enabled"]
    automation.save(update_fields=["enabled", "updated_at"])
    return {"id": str(automation.pk), "name": automation.name, "enabled": automation.enabled}


def list_leads(workspace_id, args):
    from apps.crm.models import Lead

    limit = _limit(args, 25, 50)
    query = Lead.objects.for_workspace(workspace_id).order_by("-created_at")
    search = str(args.get("search") or "")[:100]
    if search:
        query = query.filter(
            Q(name__icontains=search) | Q(email__icontains=search) | Q(handle__icontains=search)
        )
    if args.get("stage"):
        query = query.filter(stage=str(args["stage"])[:20])
    tag = str(args.get("tag") or "").strip()
    leads = [lead for lead in query[: limit * 4 if tag else limit] if not tag or tag in lead.tags]
    return {
        "leads": [
            {
                "id": str(lead.pk),
                "name": lead.name,
                "email": lead.email,
                "handle": lead.handle,
                "stage": lead.stage,
                "tags": lead.tags,
                "created_at": lead.created_at,
            }
            for lead in leads[:limit]
        ]
    }


def update_lead(workspace_id, args):
    from apps.crm.field_defs import coerce_fields
    from apps.crm.models import Lead
    from apps.crm.stages import validate_stage_for

    with transaction.atomic():
        lead = (
            Lead.objects.for_workspace(workspace_id)
            .select_for_update()
            .filter(pk=_id(args.get("lead_id"), "lead_id"))
            .first()
        )
        if not lead:
            raise ToolError("No lead with that ID in this workspace.")
        try:
            if "stage" in args:
                lead.stage = validate_stage_for(workspace_id, args["stage"])
            for name in ("add_tags", "remove_tags"):
                tags = args.get(name, [])
                if not isinstance(tags, list) or any(
                    not isinstance(t, str) or not 1 <= len(t.strip()) <= 40 for t in tags
                ):
                    raise ToolError(f"{name} must be a list of 1–40 character tags.")
            tags = [
                t for t in lead.tags if t not in {x.strip() for x in args.get("remove_tags", [])}
            ]
            tags = list(dict.fromkeys([*tags, *(t.strip() for t in args.get("add_tags", []))]))
            if len(tags) > 50:
                raise ToolError("A lead can have at most 50 tags.")
            lead.tags = tags
            fields = args.get("fields")
            if fields is not None:
                if not isinstance(fields, dict) or any(
                    not isinstance(k, str) or not 1 <= len(k) <= 60 or len(str(v)) > 500
                    for k, v in fields.items()
                ):
                    raise ToolError("fields must map short names to short values.")
                merged = {**lead.fields, **coerce_fields(workspace_id, fields)}
                if len(merged) > 50:
                    raise ToolError("A lead can have at most 50 fields.")
                lead.fields = merged
        except serializers.ValidationError as exc:
            raise ToolError(_message(exc)) from None
        lead.save()
    return {"id": str(lead.pk), "stage": lead.stage, "tags": lead.tags, "fields": lead.fields}


def list_pipeline_stages(workspace_id, args):
    from apps.crm.stages import stages_for

    return {"stages": stages_for(workspace_id)}


def list_tracking_links(workspace_id, args):
    from apps.tools.models import DeepLink

    return {
        "links": [
            {
                "id": str(link.pk),
                "title": link.title,
                "code": link.code,
                "target": link.target,
                "clicks": link.clicks,
                "active": link.active,
            }
            for link in DeepLink.objects.for_workspace(workspace_id).order_by("-created_at")[:100]
        ]
    }


def create_tracking_link(workspace_id, args):
    from apps.tenants.models import Workspace
    from apps.tools.views import DeepLinkSerializer

    data = {
        key: args[key]
        for key in ("title", "target", "code", "campaign", "source", "medium")
        if key in args
    }
    if "code" not in data:
        data["code"] = "l-" + uuid.uuid4().hex[:8]
    serializer = DeepLinkSerializer(data=data)
    if not serializer.is_valid():
        raise ToolError(_message(serializers.ValidationError(serializer.errors)))
    try:
        with transaction.atomic():
            link = serializer.save(workspace=Workspace.objects.get(pk=workspace_id))
    except IntegrityError:
        raise ToolError("That link code is already taken.") from None
    return {
        "id": str(link.pk),
        "code": link.code,
        "path": f"/go/{link.code}/",
        "target": link.target,
    }


def list_knowledge_bases(workspace_id, args):
    from apps.agents.models import KnowledgeBase, KnowledgeDocument

    docs = KnowledgeDocument.objects.for_workspace(workspace_id)
    return {
        "general_documents": docs.filter(knowledge_base=None).count(),
        "knowledge_bases": [
            {
                "id": str(base.pk),
                "name": base.name,
                "description": base.description,
                "documents": docs.filter(knowledge_base=base).count(),
            }
            for base in KnowledgeBase.objects.for_workspace(workspace_id)
        ],
    }


def add_knowledge_text(workspace_id, args):
    from apps.agents.models import KnowledgeBase, KnowledgeDocument
    from apps.billing.gating import guard

    title, text = args.get("title"), args.get("text")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
        raise ToolError("title needs 1–200 characters.")
    if not isinstance(text, str) or not 1 <= len(text) <= 250000:
        raise ToolError("text needs 1–250,000 characters.")
    if not guard(workspace_id, "ai_agent_enabled"):
        raise ToolError("This workspace's plan does not include the AI agent.")
    base = None
    if args.get("knowledge_base_id"):
        base = (
            KnowledgeBase.objects.for_workspace(workspace_id)
            .filter(pk=_id(args["knowledge_base_id"], "knowledge_base_id"))
            .first()
        )
        if not base:
            raise ToolError("No knowledge base with that ID in this workspace.")
    document = KnowledgeDocument.objects.for_workspace(workspace_id).create(
        workspace_id=workspace_id, title=title.strip(), source=text, knowledge_base=base
    )
    return {"id": str(document.pk), "status": document.status}


TAG = {"type": "string", "minLength": 1, "maxLength": 40}
EXTRA_TOOLS = {
    "list_automations": (
        list_automations,
        "read",
        "List automations with their triggers, live status and run counts.",
        _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
    ),
    "set_automation_enabled": (
        set_automation_enabled,
        "write",
        "Turn a published automation on or off.",
        _schema(
            {"automation_id": UUID, "enabled": {"type": "boolean"}}, ["automation_id", "enabled"]
        ),
    ),
    "list_leads": (
        list_leads,
        "read",
        "Search contacts by name, email or handle, optionally by stage or tag.",
        _schema(
            {
                "search": {"type": "string", "maxLength": 100},
                "stage": {"type": "string", "maxLength": 20},
                "tag": {"type": "string", "maxLength": 40},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            }
        ),
    ),
    "update_lead": (
        update_lead,
        "write",
        "Change a contact's stage, add or remove tags, or set custom fields. Does not message them.",
        _schema(
            {
                "lead_id": UUID,
                "stage": {"type": "string", "maxLength": 20},
                "add_tags": {"type": "array", "items": TAG, "maxItems": 20},
                "remove_tags": {"type": "array", "items": TAG, "maxItems": 20},
                "fields": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            ["lead_id"],
        ),
    ),
    "list_pipeline_stages": (
        list_pipeline_stages,
        "read",
        "The workspace's CRM pipeline stages, in order.",
        _schema({}),
    ),
    "list_tracking_links": (
        list_tracking_links,
        "read",
        "Tracking links with their destinations and click counts.",
        _schema({}),
    ),
    "create_tracking_link": (
        create_tracking_link,
        "write",
        "Create a trackable short link to an HTTPS destination.",
        _schema(
            {
                "title": {"type": "string", "minLength": 1, "maxLength": 80},
                "target": {"type": "string", "maxLength": 2000},
                "code": {"type": "string", "minLength": 2, "maxLength": 40},
                "campaign": {"type": "string", "maxLength": 100},
                "source": {"type": "string", "maxLength": 100},
                "medium": {"type": "string", "maxLength": 100},
            },
            ["title", "target"],
        ),
    ),
    "list_knowledge_bases": (
        list_knowledge_bases,
        "read",
        "Knowledge bases and how many documents each holds.",
        _schema({}),
    ),
    "add_knowledge_text": (
        add_knowledge_text,
        "write",
        "Add a text document to the AI knowledge (optionally to one knowledge base); "
        "it is indexed in the background.",
        _schema(
            {
                "title": {"type": "string", "minLength": 1, "maxLength": 200},
                "text": {"type": "string", "minLength": 1, "maxLength": 250000},
                "knowledge_base_id": UUID,
            },
            ["title", "text"],
        ),
    ),
}
