"""Bounded, explicit imports from connected knowledge sources."""

import json
import re
import uuid
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gating import check_feature
from apps.channels.transport import ProviderError, request
from apps.crm.integrations import credentials_for
from apps.crm.models import IntegrationConfig
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit

from .models import KnowledgeChunk, KnowledgeDocument


def source_text(config):
    if config.is_test:
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise ProviderError("test_integration_disabled")
        return "Explicit local test knowledge source. No provider data was read."
    credentials = credentials_for(config)
    token = credentials.get("api_key") or credentials.get("access_token")
    if not token:
        raise ProviderError("integration_credentials_missing")
    options = config.options
    headers = {"Authorization": f"Bearer {token}"}
    chunks = []
    if config.provider == "google_sheets":
        body = request(
            "GET",
            f"https://sheets.googleapis.com/v4/spreadsheets/{quote(options['spreadsheet_id'], safe='')}/values/{quote(options.get('range') or 'Sheet1!A:C', safe='')}",
            headers=headers,
        )
        rows = body.get("values", [])
        if not isinstance(rows, list):
            raise ProviderError("invalid_knowledge_response")
        chunks = [json.dumps(row, ensure_ascii=False) for row in rows]
    elif config.provider == "airtable":
        offset = None
        for _ in range(5):
            body = request(
                "GET",
                f"https://api.airtable.com/v0/{quote(options['base_id'], safe='')}/{quote(options['table_id'], safe='')}",
                headers=headers,
                params={"pageSize": 100, **({"offset": offset} if offset else {})},
            )
            chunks.extend(
                json.dumps(row.get("fields", {}), ensure_ascii=False)
                for row in body.get("records", [])
            )
            offset = body.get("offset")
            if not offset:
                break
        if offset:
            raise ProviderError("knowledge_source_too_large")
    elif config.provider == "notion":
        page_id = str(uuid.UUID(str(options.get("page_id", ""))))
        pending = [(page_id, None)]
        for _ in range(10):
            if not pending:
                break
            block_id, cursor = pending.pop(0)
            body = request(
                "GET",
                f"https://api.notion.com/v1/blocks/{quote(block_id, safe='')}/children",
                headers={**headers, "Notion-Version": "2025-09-03"},
                params={"page_size": 100, **({"start_cursor": cursor} if cursor else {})},
            )
            for block in body.get("results", []):
                content = block.get(block.get("type"), {})
                text = content.get("rich_text", []) if isinstance(content, dict) else []
                chunks.append(
                    "".join(
                        str(item.get("plain_text", item.get("text", {}).get("content", "")))
                        for item in text
                    )
                )
                if block.get("has_children"):
                    pending.append((str(uuid.UUID(block["id"])), None))
            if body.get("has_more"):
                if not body.get("next_cursor"):
                    raise ProviderError("invalid_knowledge_response")
                pending.append((block_id, body["next_cursor"]))
        if pending:
            raise ProviderError("knowledge_source_too_large")
    elif config.provider == "shopify":
        domain = str(options.get("shop_domain", ""))
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}\.myshopify\.com", domain):
            raise ProviderError("invalid_shop_domain")
        cursor = None
        for _ in range(5):
            body = request(
                "POST",
                f"https://{domain}/admin/api/2026-07/graphql.json",
                headers={"X-Shopify-Access-Token": token},
                json={
                    "query": 'query($cursor: String) { products(first: 100, after: $cursor, query: "status:active") { nodes { id title description onlineStoreUrl priceRangeV2 { minVariantPrice { amount currencyCode } maxVariantPrice { amount currencyCode } } } pageInfo { hasNextPage endCursor } } }',
                    "variables": {"cursor": cursor},
                },
            )
            if body.get("errors"):
                raise ProviderError("shopify_query_failed")
            products = body.get("data", {}).get("products", {})
            chunks.extend(json.dumps(row, ensure_ascii=False) for row in products.get("nodes", []))
            info = products.get("pageInfo", {})
            if not info.get("hasNextPage"):
                cursor = None
                break
            cursor = info.get("endCursor")
            if not cursor:
                raise ProviderError("invalid_knowledge_response")
        if cursor:
            raise ProviderError("knowledge_source_too_large")
    else:
        raise ProviderError("unsupported_knowledge_source")
    text = "\n".join(chunks).strip()
    if not text or len(text) > 250000:
        raise ProviderError("knowledge_source_empty_or_too_large")
    return text


class ImportKnowledgeView(APIView):
    def post(self, request, workspace_id, pk):
        member = workspace_membership(request, workspace_id, ["owner", "admin"])
        check_feature(workspace_id, "integrations_unlocked")
        check_feature(workspace_id, "ai_agent_enabled")
        config = get_object_or_404(
            IntegrationConfig.objects.for_workspace(workspace_id),
            pk=pk,
            enabled=True,
            status="active",
            provider__in=["google_sheets", "airtable", "notion", "shopify"],
        )
        try:
            source = source_text(config)
        except (ProviderError, KeyError, TypeError, ValueError):
            raise serializers.ValidationError(
                "Could not import this source. Check its credentials, permissions, destination and size; existing knowledge was preserved."
            ) from None
        title = f"Connected source: {config.provider} ({config.pk})"
        with transaction.atomic():
            # Serialize refreshes of the same source. Never replace a document while
            # its embedding worker is processing an older snapshot.
            IntegrationConfig.objects.for_workspace(workspace_id).select_for_update().get(pk=pk)
            document = (
                KnowledgeDocument.objects.for_workspace(workspace_id)
                .select_for_update()
                .filter(title=title)
                .first()
            )
            if document and document.status == "processing":
                raise serializers.ValidationError(
                    "This source is still indexing. Retry after it finishes."
                )
            if document:
                if document.source != source or document.status == "failed":
                    KnowledgeChunk.objects.for_workspace(workspace_id).filter(
                        document=document
                    ).delete()
                    document.source, document.status, document.error_code = source, "pending", ""
                    document.source_revision += 1
                    document.save()
            else:
                document = KnowledgeDocument.objects.for_workspace(workspace_id).create(
                    workspace_id=workspace_id, title=title, source=source
                )
            audit(member.workspace, request.user, "knowledge.source_imported", document.pk)
        return Response(
            {"id": document.pk, "status": document.status, "characters": len(source)}, status=202
        )
