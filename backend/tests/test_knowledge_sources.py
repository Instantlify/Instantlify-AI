import json
from unittest.mock import patch

import pytest

from apps.agents.models import KnowledgeDocument
from apps.agents.sources import source_text
from apps.channels.transport import ProviderError
from apps.crm.models import IntegrationConfig

pytestmark = pytest.mark.django_db


def config(workspace, provider, **options):
    return IntegrationConfig.objects.for_workspace(workspace).create(
        workspace=workspace,
        provider=provider,
        credentials=json.dumps({"api_key": "private-token"}),
        options=options,
    )


def test_airtable_reads_all_pages_and_never_follows_provider_urls(workspace):
    source = config(workspace, "airtable", base_id="app-one", table_id="table-one")
    with patch(
        "apps.agents.sources.request",
        side_effect=[
            {"records": [{"fields": {"Answer": "first"}}], "offset": "opaque-cursor"},
            {"records": [{"fields": {"Answer": "second"}}]},
        ],
    ) as read:
        text = source_text(source)
    assert "first" in text and "second" in text
    assert read.call_args.kwargs["params"]["offset"] == "opaque-cursor"
    assert read.call_args.args[1] == "https://api.airtable.com/v0/app-one/table-one"


def test_notion_includes_nested_text_and_pagination(workspace):
    page = "22222222-2222-4222-8222-222222222222"
    source = config(workspace, "notion", page_id=page)
    with patch(
        "apps.agents.sources.request",
        side_effect=[
            {
                "results": [
                    {
                        "id": page,
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"plain_text": "Parent"}]},
                        "has_children": True,
                    }
                ]
            },
            {
                "results": [
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"text": {"content": "Nested"}}]},
                    }
                ]
            },
        ],
    ) as read:
        assert source_text(source) == "Parent\nNested"
    assert read.call_count == 2


def test_shopify_domain_is_fixed_before_any_request(workspace):
    source = config(workspace, "shopify", shop_domain="127.0.0.1")
    with patch("apps.agents.sources.request") as read, pytest.raises(ProviderError):
        source_text(source)
    read.assert_not_called()


def test_import_refreshes_one_snapshot_and_failed_fetch_preserves_it(client, workspace):
    source = config(workspace, "google_sheets", spreadsheet_id="sheet", range="Sheet1!A:C")
    url = f"/api/workspaces/{workspace.pk}/integrations/{source.pk}/knowledge/"
    with patch("apps.agents.sources.request", return_value={"values": [["First", "Answer"]]}):
        response = client.post(url, {}, format="json")
    assert response.status_code == 202, response.content
    with patch("apps.agents.sources.request", return_value={"values": [["New", "Answer"]]}):
        assert client.post(url, {}, format="json").status_code == 202
    assert KnowledgeDocument.objects.for_workspace(workspace).count() == 1
    document = KnowledgeDocument.objects.for_workspace(workspace).get()
    assert "New" in document.source
    with patch("apps.agents.sources.request", side_effect=ProviderError()):
        assert client.post(url, {}, format="json").status_code == 400
    document.refresh_from_db()
    assert "New" in document.source
    document.status = "processing"
    document.save()
    with patch("apps.agents.sources.request", return_value={"values": [["Replacement"]]}):
        assert client.post(url, {}, format="json").status_code == 400
    document.refresh_from_db()
    assert "New" in document.source
