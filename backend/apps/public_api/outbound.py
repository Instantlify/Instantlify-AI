"""Bounded HTTPS JSON POSTs to user-selected public webhook destinations."""

import http.client
import ipaddress
import json
import socket
import ssl
import time
from urllib.parse import urlsplit

from apps.channels.transport import ProviderError


def endpoint_parts(url):
    if not isinstance(url, str) or len(url) > 2000 or any(c.isspace() for c in url):
        raise ProviderError("invalid_webhook_url")
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.port not in {None, 443}
        ):
            raise ValueError
        return parsed
    except ValueError:
        raise ProviderError("invalid_webhook_url") from None


def post_public_json(url, payload, *, authorization="", delivery_id=""):
    parsed = endpoint_parts(url)
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ProviderError("private_webhook_target")
    body = json.dumps(payload).encode()
    if len(body) > 20000:
        raise ProviderError("webhook_request_too_large")
    if (
        not isinstance(authorization, str)
        or len(authorization) > 2000
        or "\r" in authorization
        or "\n" in authorization
    ):
        raise ProviderError("invalid_webhook_authorization")
    connection = http.client.HTTPSConnection(
        parsed.hostname, timeout=10, context=ssl.create_default_context()
    )
    # Pin the validated address while HTTPSConnection retains the hostname for TLS/SNI.
    address = addresses[0][4][0]
    connection._create_connection = lambda target, timeout, source_address=None: (
        socket.create_connection((address, 443), timeout, source_address)
    )
    try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Instantlify-Workflows/1.0",
            "Idempotency-Key": delivery_id,
        }
        if authorization:
            headers["Authorization"] = authorization
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        connection.request("POST", target, body, headers)
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            raise ProviderError("webhook_rejected")
        data = bytearray()
        deadline = time.monotonic() + 15
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError("webhook_response_timeout")
            if connection.sock:
                connection.sock.settimeout(min(10, remaining))
            chunk = response.read1(8192)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 20000:
                raise ProviderError("webhook_response_too_large")
        if not data:
            return {}
        value = json.loads(data)
        if not isinstance(value, (dict, list)):
            raise ProviderError("webhook_response_not_json_object")
        return value
    finally:
        connection.close()
