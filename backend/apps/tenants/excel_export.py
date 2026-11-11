"""Portable, formula-free XLSX export of the existing credential-free snapshot."""

import json
import math
import re
import tempfile
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZIP_DEFLATED, ZipFile

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ROW_LIMIT = 1_048_575
CELL_LIMIT = 16_000  # Safe even when every Unicode character uses two UTF-16 units.
SHEET_LABELS = {
    "leads": "Contacts",
    "form_submissions": "Form responses",
    "posts": "Scheduled posts",
    "agent": "AI agent",
    "knowledge": "Knowledge documents",
    "audit": "Activity log",
}


def column(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def clean_text(value):
    return re.sub(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]",
        lambda m: f"\\u{ord(m[0]):04x}",
        value,
    )


def workbook(snapshot, field_map=None):
    """Return a seekable temporary workbook; caller owns its lifetime."""
    field_map = field_map or {}
    file = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    sheets, overflow = [], []
    used = set()

    def sheet_name(value):
        base = re.sub(r"[\[\]:*?/\\]", " ", value).strip(" '")[:31] or "Data"
        name, number = base, 2
        while name.lower() in used:
            suffix = f" {number}"
            name, number = base[: 31 - len(suffix)] + suffix, number + 1
        used.add(name.lower())
        return name

    try:
        with ZipFile(file, "w", compression=ZIP_DEFLATED) as archive:

            def write_sheet(name, headers, rows):
                name = sheet_name(name)
                sheets.append(name)
                number = len(sheets)
                with archive.open(f"xl/worksheets/sheet{number}.xml", "w") as output:

                    def put(text):
                        output.write(text.encode("utf-8"))

                    put(
                        f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{NS}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>'
                    )
                    for col, label in enumerate(headers, 1):
                        width = max(16, min(44, len(label) + 8))
                        put(f'<col min="{col}" max="{col}" width="{width}" customWidth="1"/>')
                    put("</cols><sheetData>")
                    last = 1
                    for row_number, row in enumerate(
                        [headers] if not rows else iter_rows(headers, rows), 1
                    ):
                        last = row_number
                        put(f'<row r="{row_number}">')
                        for col, value in enumerate(row, 1):
                            ref = f"{column(col)}{row_number}"
                            style = 1 if row_number == 1 else 0
                            if value is None:
                                continue
                            if isinstance(value, bool):
                                put(f'<c r="{ref}" t="b" s="{style}"><v>{int(value)}</v></c>')
                            elif (
                                type(value) in {int, float}
                                and math.isfinite(value)
                                and len(str(value).replace("-", "").replace(".", "")) <= 15
                            ):
                                put(f'<c r="{ref}" s="{style}"><v>{value}</v></c>')
                            else:
                                text = (
                                    json.dumps(value, ensure_ascii=False)
                                    if isinstance(value, (dict, list))
                                    else str(value)
                                )
                                text = clean_text(text)
                                if len(text) > CELL_LIMIT:
                                    for part, start in enumerate(
                                        range(0, len(text), CELL_LIMIT), 1
                                    ):
                                        overflow.append(
                                            [
                                                name,
                                                row_number,
                                                headers[col - 1],
                                                part,
                                                text[start : start + CELL_LIMIT],
                                            ]
                                        )
                                    text = "Long content preserved in the Long text sheet; match sheet, row and column."
                                put(
                                    f'<c r="{ref}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{escape(text)}</t></is></c>'
                                )
                        put("</row>")
                    put(
                        f'</sheetData><autoFilter ref="A1:{column(max(1, len(headers)))}{last}"/></worksheet>'
                    )

            manifest = snapshot.get("manifest", {})
            summary = [
                ["Workspace export", "Instantlify"],
                *[[key.replace("_", " ").title(), value] for key, value in manifest.items()],
                [
                    "Notes",
                    "Nested settings are preserved as text. Long cells are continued on the Long text sheet. All exported text is stored as text, never executable formulas.",
                ],
                *[
                    [SHEET_LABELS.get(name, name.replace("_", " ").title()), len(rows)]
                    for name, rows in snapshot.items()
                    if isinstance(rows, list)
                ],
            ]
            write_sheet("Overview", ["Category", "Value"], summary)
            for name, rows in snapshot.items():
                if name == "manifest" or not isinstance(rows, list):
                    continue
                keys = list(dict.fromkeys(key for row in rows for key in row)) or field_map.get(
                    name, ["No records"]
                )
                for start in range(0, max(1, len(rows)), ROW_LIMIT):
                    label = SHEET_LABELS.get(name, name.replace("_", " ").title()) + (
                        f" {start // ROW_LIMIT + 1}" if start else ""
                    )
                    write_sheet(
                        label,
                        [key.replace("_", " ").title() for key in keys],
                        [[row.get(key) for key in keys] for row in rows[start : start + ROW_LIMIT]],
                    )
            if overflow:
                write_sheet(
                    "Long text", ["Sheet", "Excel row", "Column", "Part", "Content"], overflow
                )
            relations = "".join(
                f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{relations}<Relationship Id="styles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
            )
            archive.writestr(
                "xl/workbook.xml",
                f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                + "".join(
                    f'<sheet name={quoteattr(name)} sheetId="{i}" r:id="rId{i}"/>'
                    for i, name in enumerate(sheets, 1)
                )
                + "</sheets></workbook>",
            )
            archive.writestr(
                "_rels/.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="workbook" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
            )
            archive.writestr(
                "[Content_Types].xml",
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                + "".join(
                    f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    for i in range(1, len(sheets) + 1)
                )
                + "</Types>",
            )
            archive.writestr(
                "xl/styles.xml",
                f'<styleSheet xmlns="{NS}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF10244A"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf fontId="0" fillId="0" borderId="0" xfId="0"><alignment vertical="top" wrapText="1"/></xf><xf fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
            )
        file.seek(0)
        return file
    except Exception:
        file.close()
        raise


def iter_rows(headers, rows):
    yield headers
    yield from rows
