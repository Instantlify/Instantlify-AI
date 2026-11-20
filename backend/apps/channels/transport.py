"""Bounded HTTP calls. Provider response bodies and secrets never enter exceptions."""

import email.utils
from datetime import UTC, datetime

import httpx


class ProviderError(Exception):
    def __init__(self, code="provider_rejected", *, upstream_code=None, upstream_subcode=None):
        self.code = code
        self.upstream_code = upstream_code if type(upstream_code) is int else None
        self.upstream_subcode = upstream_subcode if type(upstream_subcode) is int else None
        super().__init__(code)


class RetryableError(ProviderError):
    def __init__(self, delay=30):
        self.delay = max(1, min(int(delay), 86400))
        super().__init__("rate_limited")


class AmbiguousDelivery(ProviderError):
    def __init__(self):
        super().__init__("delivery_unknown")


def retry_after(value):
    try:
        return max(1, int(value))
    except (ValueError, TypeError):
        try:
            return max(
                1,
                int((email.utils.parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()),
            )
        except (ValueError, TypeError, AttributeError):
            return 30


def request(method, url, *, side_effect=False, **kwargs):
    from urllib.parse import urlsplit

    from apps.platform_ops.metrics import increment

    meta = urlsplit(url).hostname in {
        "graph.instagram.com",
        "api.instagram.com",
        "graph.facebook.com",
    }
    if meta:
        increment("meta.calls")
    try:
        return _request(method, url, side_effect=side_effect, **kwargs)
    except ProviderError:
        if meta:
            increment("meta.errors")
        raise


def _request(method, url, *, side_effect=False, empty_success=False, **kwargs):
    try:
        response = httpx.request(
            method, url, timeout=httpx.Timeout(15, connect=5), follow_redirects=False, **kwargs
        )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise RetryableError(15) from None
    except httpx.HTTPError:
        if side_effect:
            raise AmbiguousDelivery() from None
        raise RetryableError(30) from None
    if response.status_code == 429:
        raise RetryableError(retry_after(response.headers.get("Retry-After")))
    if response.status_code >= 500:
        if side_effect:
            raise AmbiguousDelivery()
        raise RetryableError(30)
    if empty_success and response.status_code in {202, 204} and not response.content:
        return {"accepted": True, "status_code": response.status_code}
    try:
        body = response.json()
    except ValueError:
        if side_effect and response.is_success:
            raise AmbiguousDelivery() from None
        raise ProviderError("invalid_provider_response") from None
    if not response.is_success:
        error = body.get("error")
        if isinstance(error, dict) and any(
            isinstance(detail, dict) and detail.get("reason") == "API_KEY_INVALID"
            for detail in (error.get("details") or [])
        ):
            raise ProviderError("invalid_api_key")
        code = body.get("error", {}).get("code") if isinstance(body.get("error"), dict) else None
        if code in {4, 17, 32, 613, 80004}:
            raise RetryableError(60)
        raise ProviderError(
            "credentials_expired"
            if response.status_code == 401 or code == 190
            else "provider_rejected",
            upstream_code=code,
            upstream_subcode=error.get("error_subcode") if isinstance(error, dict) else None,
        )
    return body
