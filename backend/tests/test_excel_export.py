import json
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from apps.tenants.excel_export import MIME, NS, workbook
from apps.tenants.models import DataOperation


def test_workbook_sheets_text_safety_and_long_content():
    long_text = "🙂" * 33000
    file = workbook(
        {
            "manifest": {"workspace_id": "w"},
            "contacts": [
                {
                    "name": '=HYPERLINK("https://bad.example")',
                    "notes": long_text,
                    "tags": ["a", "b"],
                }
            ],
            "messages": [],
        },
        {"messages": ["id", "text"]},
    )
    with ZipFile(file) as archive:
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        assert [s.attrib["name"] for s in book.findall(f"{{{NS}}}sheets/{{{NS}}}sheet")] == [
            "Overview",
            "Contacts",
            "Messages",
            "Long text",
        ]
        contacts = ET.fromstring(archive.read("xl/worksheets/sheet2.xml"))
        assert not contacts.findall(f".//{{{NS}}}f")
        assert contacts.find(f".//{{{NS}}}c[@r='A2']").attrib["t"] == "inlineStr"
        overflow = ET.fromstring(archive.read("xl/worksheets/sheet4.xml"))
        chunks = [
            row.findall(f"{{{NS}}}c")[-1].find(f"{{{NS}}}is/{{{NS}}}t").text
            for row in overflow.findall(f"{{{NS}}}sheetData/{{{NS}}}row")[1:]
        ]
        assert "".join(chunks) == long_text
        assert (
            contacts.find(f"{{{NS}}}sheetViews/{{{NS}}}sheetView/{{{NS}}}pane").attrib["state"]
            == "frozen"
        )
    file.close()


@pytest.mark.django_db
def test_owner_download_defaults_to_excel_and_supports_legacy_json(client, workspace):
    job = DataOperation.objects.for_workspace(workspace).create(
        workspace=workspace,
        kind="export",
        status="complete",
        result=json.dumps({"manifest": {}, "contacts": [{"name": "Alex"}]}),
    )
    url = f"/api/workspaces/{workspace.pk}/data-operations/{job.pk}/download/"
    response = client.get(url)
    assert response.status_code == 200 and response["Content-Type"] == MIME
    assert ".xlsx" in response["Content-Disposition"] and "no-store" in response["Cache-Control"]
    with ZipFile(BytesIO(b"".join(response.streaming_content))) as archive:
        assert "xl/workbook.xml" in archive.namelist()
    assert client.get(url, {"format": "json"}).json()["contacts"][0]["name"] == "Alex"
