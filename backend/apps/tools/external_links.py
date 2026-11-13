"""User-initiated browser handoff; embedded browsers retain final control."""

from urllib.parse import quote, urlsplit, urlunsplit

from django.http import HttpResponse
from django.utils.html import escape


def external_browser_page(request, destination):
    agent = request.META.get("HTTP_USER_AGENT", "")[:1000]
    if not any(marker in agent for marker in ["Instagram", "FBAN", "FBAV", "TikTok", "Line/"]):
        return None
    parsed = urlsplit(destination)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        return None
    chrome = ""
    if "Android" in agent:
        # Quote intent delimiters; only our fixed Chrome package can be selected.
        path = quote(parsed.path, safe="/%:@")
        query = quote(parsed.query, safe="=&%:+,/?@")
        fallback = quote(urlunsplit(parsed._replace(fragment="")), safe="")
        intent = f"intent://{parsed.netloc}{path}{'?' + query if query else ''}#Intent;scheme={parsed.scheme};package=com.android.chrome;S.browser_fallback_url={fallback};end"
        chrome = f'<p><a class="button" href="{escape(intent)}">Open in Chrome</a></p>'
    response = HttpResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Open in your browser | Instantlify</title><style>"
        "body{font:16px/1.6 system-ui;margin:0;background:#101b20;color:#edf4f1;display:grid;min-height:100dvh;place-items:center}"
        "main{max-width:32rem;padding:2rem;overflow-wrap:anywhere}a{color:#b4f46d}.button{display:inline-block;border:1px solid;padding:.7rem 1rem;border-radius:.5rem}"
        "input{box-sizing:border-box;width:100%;padding:.7rem;border-radius:.4rem}</style></head><body><main>"
        "<h1>Open in your browser</h1><p>For the full experience, open this page in your regular browser.</p>"
        + chrome
        + "<p>If the app blocks this button, use its menu and choose <strong>Open in browser</strong> or <strong>Open in Safari</strong>. You can also copy the address below into your browser.</p>"
        + f'<label>Website address<input readonly value="{escape(destination)}"></label>'
        + f'<p><a href="{escape(destination)}" target="_blank" rel="external noopener noreferrer">Continue to website</a></p>'
        + "<p>Some apps keep links inside their own browser. Your browser controls whether it can open another app.</p></main></body></html>",
        content_type="text/html",
    )
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response
