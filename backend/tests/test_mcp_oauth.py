import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import Client
from rest_framework.test import APIClient

from apps.public_api.models import APIKey

pytestmark = pytest.mark.django_db

REDIRECT = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture(autouse=True)
def public_url(settings):
    settings.PUBLIC_APP_URL = "https://app.example.com"


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode()
    return verifier, challenge.rstrip("=")


def register():
    res = APIClient().post(
        "/api/oauth/register/",
        {"redirect_uris": [REDIRECT], "client_name": "Claude"},
        format="json",
    )
    assert res.status_code == 201, res.content
    return res.json()["client_id"]


def authorize(client_id, challenge, scope="read write"):
    res = Client().get(
        "/api/oauth/authorize/",
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "scope": scope,
            "resource": "https://app.example.com/api/mcp/",
        },
    )
    assert res.status_code == 302, res.content
    return parse_qs(urlsplit(res["Location"]).query)["request"][0]


def approve(owner, request_id, workspace, scopes=("read", "write")):
    res = owner.post(
        f"/api/oauth/requests/{request_id}/",
        {"decision": "approve", "workspace_id": str(workspace.pk), "scopes": list(scopes)},
        format="json",
    )
    assert res.status_code == 200, res.content
    query = parse_qs(urlsplit(res.json()["redirect"]).query)
    assert query["state"] == ["xyz"]
    return query["code"][0]


def exchange(client_id, code, verifier):
    return Client().post(
        "/api/oauth/token/",
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": REDIRECT,
            "code_verifier": verifier,
        },
    )


def mcp(token, method="tools/list"):
    return APIClient().post(
        "/api/mcp/",
        {"jsonrpc": "2.0", "id": 1, "method": method},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


def test_discovery_documents_and_unauthenticated_challenge():
    resource = Client().get("/.well-known/oauth-protected-resource").json()
    assert resource["resource"] == "https://app.example.com/api/mcp/"
    assert resource["authorization_servers"] == ["https://app.example.com"]
    server = Client().get("/.well-known/oauth-authorization-server").json()
    assert server["code_challenge_methods_supported"] == ["S256"]
    assert server["registration_endpoint"] == "https://app.example.com/api/oauth/register/"
    res = APIClient().post(
        "/api/mcp/", {"jsonrpc": "2.0", "id": 1, "method": "ping"}, format="json"
    )
    assert res.status_code == 401
    assert (
        'resource_metadata="https://app.example.com/.well-known/oauth-protected-resource"'
        in (res["WWW-Authenticate"])
    )


def test_full_flow_tokens_work_rotate_and_revoke(client, workspace):
    client_id = register()
    verifier, challenge = pkce()
    request_id = authorize(client_id, challenge)
    consent = client.get(f"/api/oauth/requests/{request_id}/").json()
    assert consent["client_name"] == "Claude" and consent["redirect_host"] == "claude.ai"
    assert {"id": str(workspace.pk), "name": workspace.name} in consent["workspaces"]
    code = approve(client, request_id, workspace)

    tokens = exchange(client_id, code, verifier).json()
    assert tokens["token_type"] == "Bearer" and tokens["scope"] == "read write"
    listed = mcp(tokens["access_token"])
    assert listed.status_code == 200 and listed.json()["result"]["tools"]

    # The code works once; a replay fails and revokes what it produced.
    assert exchange(client_id, code, verifier).status_code == 400
    assert mcp(tokens["access_token"]).status_code == 401

    # A fresh grant, then refresh rotation.
    request_id = authorize(client_id, challenge)
    tokens = exchange(client_id, approve(client, request_id, workspace), verifier).json()
    refreshed = (
        Client()
        .post(
            "/api/oauth/token/",
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": tokens["refresh_token"],
            },
        )
        .json()
    )
    assert mcp(refreshed["access_token"]).status_code == 200
    reuse = Client().post(
        "/api/oauth/token/",
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
        },
    )
    assert reuse.status_code == 400

    # Revoking the backing API key in Instantlify ends the connection.
    APIKey.objects.for_workspace(workspace).update(revoked_at="2026-01-01T00:00:00Z")
    assert mcp(refreshed["access_token"]).status_code == 401


def test_pkce_and_redirect_are_enforced(client, workspace):
    client_id = register()
    verifier, challenge = pkce()
    code = approve(client, authorize(client_id, challenge), workspace)
    assert exchange(client_id, code, "wrong-verifier-" + "x" * 40).status_code == 400
    bad = Client().get(
        "/api/oauth/authorize/",
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://evil.example.com/cb",
        },
    )
    assert bad.status_code == 400  # never redirects to an unregistered URI
    no_pkce = Client().get(
        "/api/oauth/authorize/",
        {"response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "state": "s"},
    )
    assert "error=invalid_request" in no_pkce["Location"]


def test_read_only_grants_cannot_write_and_consent_rules(client, workspace):
    client_id = register()
    verifier, challenge = pkce()
    request_id = authorize(client_id, challenge)
    assert (
        client.post(
            f"/api/oauth/requests/{request_id}/",
            {"decision": "approve", "workspace_id": str(workspace.pk), "scopes": []},
            format="json",
        ).status_code
        == 400
    )
    tokens = exchange(client_id, approve(client, request_id, workspace, ("read",)), verifier).json()
    assert tokens["scope"] == "read"
    call = APIClient().post(
        "/api/mcp/",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "update_lead", "arguments": {"lead_id": str(workspace.pk)}},
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
    )
    assert call.json()["result"]["isError"] is True

    # Denying sends the user back with access_denied.
    request_id = authorize(client_id, challenge)
    denied = client.post(f"/api/oauth/requests/{request_id}/", {"decision": "deny"}, format="json")
    assert "error=access_denied" in denied.json()["redirect"]


def test_registration_rejects_unsafe_redirects():
    for uris in (["http://evil.example.com/cb"], ["javascript:alert(1)"], []):
        res = APIClient().post("/api/oauth/register/", {"redirect_uris": uris}, format="json")
        assert res.status_code == 400
    ok = APIClient().post(
        "/api/oauth/register/", {"redirect_uris": ["http://localhost:3333/cb"]}, format="json"
    )
    assert ok.status_code == 201
