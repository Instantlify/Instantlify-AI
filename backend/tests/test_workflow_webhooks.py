import json
from unittest.mock import MagicMock, patch

import pytest

from apps.channels.transport import ProviderError
from apps.public_api.outbound import post_public_json


def endpoint(ip="93.184.216.34"):
    return [(2, 1, 6, "", (ip, 443))]


def connection(status=200, chunks=None):
    transport = MagicMock()
    transport.getresponse.return_value.status = status
    transport.getresponse.return_value.read1.side_effect = chunks or [
        b'{"order":{"id":"ord-1"}}',
        b"",
    ]
    return transport


def test_webhook_pins_public_address_and_keeps_original_tls_hostname():
    transport = connection()
    with (
        patch("apps.public_api.outbound.socket.getaddrinfo", return_value=endpoint()) as dns,
        patch(
            "apps.public_api.outbound.http.client.HTTPSConnection", return_value=transport
        ) as https,
        patch("apps.public_api.outbound.socket.create_connection") as connect,
    ):
        result = post_public_json(
            "https://workflow.example/hook?key=private",
            {"message": 'hello "friend"'},
            authorization="Bearer private",
            delivery_id="stable-key",
        )
        transport._create_connection(("changed.example", 443), 10)
    assert result == {"order": {"id": "ord-1"}}
    assert dns.call_count == 1
    assert https.call_args.args == ("workflow.example",)
    assert connect.call_args.args == (("93.184.216.34", 443), 10, None)
    method, path, body, headers = transport.request.call_args.args
    assert method == "POST" and path == "/hook?key=private"
    assert json.loads(body) == {"message": 'hello "friend"'}
    assert headers["Idempotency-Key"] == "stable-key"
    transport.close.assert_called_once()


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_webhooks_refuse_private_targets_before_connecting(ip):
    with (
        patch("apps.public_api.outbound.socket.getaddrinfo", return_value=endpoint(ip)),
        patch("apps.public_api.outbound.http.client.HTTPSConnection") as https,
    ):
        with pytest.raises(ProviderError, match="private_webhook_target"):
            post_public_json("https://workflow.example/", {})
    https.assert_not_called()


@pytest.mark.parametrize(
    "status,chunks,reason",
    [
        (302, None, "webhook_rejected"),
        (200, [b"a" * 20001], "webhook_response_too_large"),
        (200, [b"42", b""], "webhook_response_not_json_object"),
    ],
)
def test_webhook_redirects_and_unbounded_or_scalar_responses_are_rejected(status, chunks, reason):
    transport = connection(status, chunks)
    with (
        patch("apps.public_api.outbound.socket.getaddrinfo", return_value=endpoint()),
        patch("apps.public_api.outbound.http.client.HTTPSConnection", return_value=transport),
    ):
        with pytest.raises(ProviderError, match=reason):
            post_public_json("https://workflow.example/", {})
    assert transport.request.call_count == 1
    transport.close.assert_called_once()
