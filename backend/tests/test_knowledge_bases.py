import io
import zipfile
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.agents.models import AgentConfig, KnowledgeDocument
from apps.agents.web_import import ImportError_, docx_text, fetch_page, html_to_text
from tests.conftest import set_limits

pytestmark = pytest.mark.django_db


@pytest.fixture
def config(workspace):
    set_limits(workspace, ai_agent_enabled=True)
    return AgentConfig.objects.for_workspace(workspace).create(
        workspace=workspace, enabled=True, is_test=True
    )


def make_docx(*paragraphs):
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def test_bases_group_documents_and_deleting_keeps_documents(client, workspace, config):
    bases = f"/api/workspaces/{workspace.pk}/knowledge-bases/"
    docs = f"/api/workspaces/{workspace.pk}/documents/"
    base = client.post(bases, {"name": "Pricing", "description": "Plans"}, format="json").json()
    added = client.post(
        docs,
        {"title": "Plans", "source": "Pro is $20", "knowledge_base": base["id"]},
        format="json",
    )
    assert added.status_code == 202, added.content
    assert added.json()["knowledge_base"] == base["id"]
    assert client.get(bases).json()[0]["document_count"] == 1
    bad = client.post(docs, {"source": "x", "knowledge_base": "not-a-uuid"}, format="json")
    assert bad.status_code == 400
    assert client.delete(f"{bases}{base['id']}/").status_code == 204
    assert KnowledgeDocument.objects.for_workspace(workspace).get().knowledge_base is None


def test_url_and_docx_sources_are_queued_and_ingested(client, workspace, config):
    docs = f"/api/workspaces/{workspace.pk}/documents/"
    assert client.post(docs, {"url": "http://example.com"}, format="json").status_code == 400
    queued = client.post(docs, {"url": "https://example.com/faq"}, format="json")
    assert queued.status_code == 202 and queued.json()["file_type"] == "url"
    upload = client.post(
        docs,
        {
            "file": SimpleUploadedFile(
                "faq.docx", make_docx("Refunds within 30 days", "Ships worldwide")
            )
        },
        format="multipart",
    )
    assert upload.status_code == 202 and upload.json()["file_type"] == "docx"

    from apps.agents.rag import ingest

    page = KnowledgeDocument.objects.for_workspace(workspace).get(file_type="url")
    with patch("apps.agents.web_import.fetch_page", return_value=("FAQ", "We open at 9am daily.")):
        ingest(page, config)
    doc = KnowledgeDocument.objects.for_workspace(workspace).get(file_type="docx")
    ingest(doc, config)
    statuses = set(
        KnowledgeDocument.objects.for_workspace(workspace).values_list("status", flat=True)
    )
    assert statuses == {"ready"}


def test_docx_and_html_extraction():
    assert docx_text(make_docx("One", "Two")) == "One\nTwo"
    with pytest.raises(ImportError_):
        docx_text(b"not a zip")
    title, text = html_to_text(
        "<html><head><title>Help</title><style>x{}</style></head>"
        "<body><h1>Hours</h1><p>Open&nbsp;9&ndash;5</p><script>evil()</script></body></html>"
    )
    assert title == "Help"
    assert "Hours" in text and "Open\xa09–5" in text and "evil" not in text


@pytest.mark.parametrize(
    "url", ["http://example.com", "https://user:pw@example.com", "ftp://example.com", "https://"]
)
def test_page_urls_must_be_plain_https(url):
    with pytest.raises(ImportError_):
        fetch_page(url)


def test_private_addresses_are_refused():
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.5", 443))]):
        with pytest.raises(ImportError_, match="private_address"):
            fetch_page("https://internal.example.com/")
