"""Text extraction for knowledge sources: public web pages and DOCX files.

Web pages are fetched over HTTPS only, from public addresses only (the resolved address
is checked and pinned, and every redirect is re-checked), with size and time limits, so
a pasted URL can never reach the platform's internal network. DOCX files are read with
the standard library from word/document.xml, with zip-bomb and entity guards.
"""

import http.client
import io
import ipaddress
import re
import socket
import ssl
import time
import zipfile
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_DOCX_XML = 10 * 1024 * 1024


class ImportError_(ValueError):
    """A source that cannot be imported; the message is a stable error code."""


def validate_page_url(url):
    if not isinstance(url, str) or len(url) > 2000 or any(c.isspace() for c in url):
        raise ImportError_("invalid_url")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
    ):
        raise ImportError_("invalid_url")
    return parsed


def _public_address(hostname):
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ImportError_("host_not_found") from None
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ImportError_("private_address")
    return addresses[0][4][0]


def _get(parsed):
    address = _public_address(parsed.hostname)
    connection = http.client.HTTPSConnection(
        parsed.hostname, timeout=10, context=ssl.create_default_context()
    )
    connection._create_connection = lambda target, timeout, source_address=None: (
        socket.create_connection((address, 443), timeout, source_address)
    )
    target = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
    try:
        connection.request(
            "GET",
            target,
            headers={"User-Agent": "Instantlify-Knowledge/1.0", "Accept": "text/html,text/plain"},
        )
        response = connection.getresponse()
        if response.status in {301, 302, 303, 307, 308}:
            return response.status, response.getheader("Location", ""), "", b""
        if response.status != 200:
            raise ImportError_("page_unavailable")
        kind = (response.getheader("Content-Type") or "").split(";")[0].strip().lower()
        if kind not in {"text/html", "text/plain", "application/xhtml+xml"}:
            raise ImportError_("unsupported_page_type")
        data, deadline = bytearray(), time.monotonic() + 15
        while True:
            if time.monotonic() > deadline:
                raise ImportError_("page_timeout")
            chunk = response.read1(65536)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_PAGE_BYTES:
                raise ImportError_("page_too_large")
        charset = re.search(r"charset=([\w-]+)", response.getheader("Content-Type") or "")
        return 200, "", kind, bytes(data), (charset.group(1) if charset else "utf-8")
    except (OSError, http.client.HTTPException):
        raise ImportError_("page_unavailable") from None
    finally:
        connection.close()


def fetch_page(url):
    """(title, text) of a public web page."""
    parsed = validate_page_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        result = _get(parsed)
        if result[0] != 200:
            parsed = validate_page_url(urljoin(parsed.geturl(), result[1]))
            continue
        _, _, kind, body, charset = result
        try:
            text = body.decode(charset, errors="replace")
        except LookupError:
            text = body.decode("utf-8", errors="replace")
        if kind == "text/plain":
            return parsed.hostname, text
        return html_to_text(text)
    raise ImportError_("too_many_redirects")


class _Extractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title, self.skipping, self.in_title = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        elif tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag in self.SKIP and self.skipping:
            self.skipping -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.skipping:
            self.parts.append(data)


def html_to_text(html):
    parser = _Extractor()
    parser.feed(html)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return parser.title.strip()[:200], text


def docx_text(data):
    """Paragraph text of a .docx file."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        info = archive.getinfo("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        raise ImportError_("invalid_docx") from None
    if info.file_size > MAX_DOCX_XML:
        raise ImportError_("document_size_or_empty")
    xml = archive.read(info)
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ImportError_("invalid_docx")
    from xml.etree import ElementTree

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        raise ImportError_("invalid_docx") from None
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{ns}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{ns}t"))
        if text.strip():
            paragraphs.append(text)
    return "\n".join(paragraphs)
