"""OAuth 2.1 authorization server for the MCP endpoint (MCP authorization profile).

Discovery (RFC 9728 protected-resource metadata, RFC 8414 server metadata), dynamic
client registration (RFC 7591) for public clients, authorization code with mandatory
PKCE S256, and refresh-token rotation. Consent happens in the Nemio app: the signed-in
user picks a workspace they own or administer and the scopes to grant. Every approved
grant creates a workspace API key; access tokens resolve to it, so revoking that key
ends the connection and the MCP tools behave exactly as with a pasted key.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import APIKey, OAuthAuthorization, OAuthClient, OAuthToken

ACCESS_PREFIX = "nmo_"
REFRESH_PREFIX = "nmr_"
ACCESS_TTL = timedelta(hours=1)
REFRESH_TTL = timedelta(days=30)
CODE_TTL = timedelta(minutes=10)
SCOPES = ("read", "write")


def base_url():
    return settings.PUBLIC_APP_URL.rstrip("/")


def resource_url():
    return base_url() + "/api/mcp/"


def resource_metadata_url():
    return base_url() + "/.well-known/oauth-protected-resource"


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def protected_resource_metadata(request, *args):
    return JsonResponse(
        {
            "resource": resource_url(),
            "authorization_servers": [base_url()],
            "scopes_supported": list(SCOPES),
            "bearer_methods_supported": ["header"],
            "resource_name": "Nemio",
        }
    )


def authorization_server_metadata(request, *args):
    root = base_url()
    return JsonResponse(
        {
            "issuer": root,
            "authorization_endpoint": root + "/api/oauth/authorize/",
            "token_endpoint": root + "/api/oauth/token/",
            "registration_endpoint": root + "/api/oauth/register/",
            "scopes_supported": list(SCOPES),
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
        }
    )


def _valid_redirect(uri):
    """HTTPS, or http on a loopback host for desktop clients; no fragments."""
    if not isinstance(uri, str) or len(uri) > 2000 or any(c.isspace() for c in uri):
        return False
    try:
        parts = urlsplit(uri)
    except ValueError:
        return False
    if parts.fragment or not parts.hostname or parts.username or parts.password:
        return False
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        uris = request.data.get("redirect_uris")
        if (
            not isinstance(uris, list)
            or not 1 <= len(uris) <= 10
            or not all(_valid_redirect(uri) for uri in uris)
        ):
            return Response(
                {
                    "error": "invalid_redirect_uri",
                    "error_description": "Provide 1-10 HTTPS (or loopback) redirect URIs.",
                },
                status=400,
            )
        method = request.data.get("token_endpoint_auth_method", "none")
        if method != "none":
            return Response(
                {
                    "error": "invalid_client_metadata",
                    "error_description": "Only public clients (auth method none) are supported.",
                },
                status=400,
            )
        client = OAuthClient.objects.create(
            client_id="nmc_" + secrets.token_urlsafe(24),
            client_name=str(request.data.get("client_name") or "MCP client")[:100],
            redirect_uris=list(dict.fromkeys(uris)),
        )
        return Response(
            {
                "client_id": client.client_id,
                "client_name": client.client_name,
                "redirect_uris": client.redirect_uris,
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "client_id_issued_at": int(client.created_at.timestamp()),
            },
            status=201,
        )


def _error_redirect(redirect_uri, error, state):
    query = {"error": error}
    if state:
        query["state"] = state
    separator = "&" if "?" in redirect_uri else "?"
    return HttpResponseRedirect(redirect_uri + separator + urlencode(query))


def authorize(request):
    """Validate the request, then hand the user to the in-app consent screen."""
    params = request.GET
    client = OAuthClient.objects.filter(client_id=params.get("client_id", "")).first()
    redirect_uri = params.get("redirect_uri", "")
    # Never redirect to an unregistered URI: show an error instead.
    if client is None or redirect_uri not in client.redirect_uris:
        return JsonResponse(
            {"error": "invalid_request", "error_description": "Unknown client or redirect URI."},
            status=400,
        )
    state = params.get("state", "")[:500]
    if params.get("response_type") != "code":
        return _error_redirect(redirect_uri, "unsupported_response_type", state)
    challenge = params.get("code_challenge", "")
    if params.get("code_challenge_method") != "S256" or not 43 <= len(challenge) <= 128:
        return _error_redirect(redirect_uri, "invalid_request", state)
    resource = params.get("resource")
    if resource and resource.rstrip("/") != resource_url().rstrip("/"):
        return _error_redirect(redirect_uri, "invalid_target", state)
    requested = [scope for scope in params.get("scope", "read write").split() if scope in SCOPES]
    grant = OAuthAuthorization.objects.create(
        client=client,
        redirect_uri=redirect_uri,
        code_challenge=challenge,
        state=state,
        scopes=requested or ["read"],
        expires_at=timezone.now() + CODE_TTL,
    )
    return HttpResponseRedirect(f"{base_url()}/connect/authorize/?request={grant.pk}")


class ConsentView(APIView):
    """The signed-in user's view of a pending request, and their decision."""

    def _grant(self, pk):
        grant = get_object_or_404(OAuthAuthorization.objects.select_related("client"), pk=pk)
        if grant.status != "pending" or grant.expires_at < timezone.now():
            raise serializers.ValidationError("This connection request has expired. Start again.")
        return grant

    @staticmethod
    def _workspaces(user):
        from apps.tenants.models import Membership

        return [
            {"id": str(member.workspace_id), "name": member.workspace.name}
            for member in Membership.all_objects.filter(
                user=user, role__in=["owner", "admin"]
            ).select_related("workspace")
        ]

    def get(self, request, pk):
        grant = self._grant(pk)
        return Response(
            {
                "client_name": grant.client.client_name,
                "redirect_host": urlsplit(grant.redirect_uri).hostname,
                "scopes": grant.scopes,
                "workspaces": self._workspaces(request.user),
            }
        )

    def post(self, request, pk):
        with transaction.atomic():
            grant = self._grant(pk)
            grant = OAuthAuthorization.objects.select_for_update().get(pk=grant.pk)
            if request.data.get("decision") != "approve":
                grant.status = "denied"
                grant.save(update_fields=["status"])
                return Response(
                    {
                        "redirect": _error_redirect(
                            grant.redirect_uri, "access_denied", grant.state
                        ).url
                    }
                )
            workspace_id = str(request.data.get("workspace_id") or "")
            if workspace_id not in {item["id"] for item in self._workspaces(request.user)}:
                raise serializers.ValidationError("Choose a workspace you own or administer.")
            scopes = [scope for scope in request.data.get("scopes") or [] if scope in grant.scopes]
            if "read" not in scopes:
                raise serializers.ValidationError("Read access is required.")
            code = secrets.token_urlsafe(32)
            grant.user = request.user
            grant.workspace_id = workspace_id
            grant.scopes = scopes
            grant.code_hash = _hash(code)
            grant.status = "approved"
            grant.expires_at = timezone.now() + CODE_TTL
            grant.save()
        query = {"code": code}
        if grant.state:
            query["state"] = grant.state
        separator = "&" if "?" in grant.redirect_uri else "?"
        return Response({"redirect": grant.redirect_uri + separator + urlencode(query)})


def _token_error(error, description=""):
    body = {"error": error}
    if description:
        body["error_description"] = description
    response = JsonResponse(body, status=400)
    response["Cache-Control"] = "no-store"
    return response


def _issue(token=None, *, client=None, api_key=None, authorization=None):
    access = ACCESS_PREFIX + secrets.token_urlsafe(32)
    refresh = REFRESH_PREFIX + secrets.token_urlsafe(32)
    now = timezone.now()
    if token is None:
        token = OAuthToken(client=client, api_key=api_key, authorization=authorization)
    token.access_hash = _hash(access)
    token.refresh_hash = _hash(refresh)
    token.access_expires_at = now + ACCESS_TTL
    token.refresh_expires_at = now + REFRESH_TTL
    token.save()
    response = JsonResponse(
        {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": int(ACCESS_TTL.total_seconds()),
            "refresh_token": refresh,
            "scope": " ".join(token.api_key.scopes),
        }
    )
    response["Cache-Control"] = "no-store"
    return response


def _pkce_ok(verifier, challenge):
    if not 43 <= len(verifier) <= 128:
        return False
    digest = hashlib.sha256(verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return hmac.compare_digest(expected, challenge)


@csrf_exempt
def token(request):
    if request.method != "POST":
        return JsonResponse({"error": "invalid_request"}, status=405)
    data = request.POST
    client = OAuthClient.objects.filter(client_id=data.get("client_id", "")).first()
    if client is None:
        return _token_error("invalid_client")
    if data.get("grant_type") == "authorization_code":
        return _exchange_code(client, data)
    if data.get("grant_type") == "refresh_token":
        return _refresh(client, data)
    return _token_error("unsupported_grant_type")


def _exchange_code(client, data):
    from apps.tenants.services import audit

    from .auth import generate_key

    with transaction.atomic():
        grant = (
            OAuthAuthorization.objects.select_for_update()
            .filter(code_hash=_hash(data.get("code", "")), client=client)
            .exclude(code_hash="")
            .first()
        )
        if (
            grant is None
            or grant.status != "approved"
            or grant.expires_at < timezone.now()
            or data.get("redirect_uri") != grant.redirect_uri
            or not _pkce_ok(data.get("code_verifier", ""), grant.code_challenge)
        ):
            if grant is not None and grant.status == "used":
                # A replayed code revokes everything it produced (RFC 6749 4.1.2).
                OAuthToken.objects.filter(authorization=grant).update(revoked_at=timezone.now())
            return _token_error("invalid_grant")
        grant.status = "used"
        grant.save(update_fields=["status"])
        raw, prefix, digest = generate_key()
        api_key = APIKey.objects.for_workspace(grant.workspace_id).create(
            workspace_id=grant.workspace_id,
            name=f"{client.client_name} (connector)"[:80],
            prefix=prefix,
            key_hash=digest,
            scopes=grant.scopes,
            created_by=grant.user,
        )
        # The key itself is never used directly; tokens resolve to it.
        del raw
        audit(api_key.workspace, grant.user, "mcp.oauth_connected", api_key.pk)
        return _issue(client=client, api_key=api_key, authorization=grant)


def _refresh(client, data):
    with transaction.atomic():
        current = (
            OAuthToken.objects.select_for_update()
            .select_related("api_key")
            .filter(refresh_hash=_hash(data.get("refresh_token", "")), client=client)
            .first()
        )
        if (
            current is None
            or current.revoked_at
            or current.refresh_expires_at < timezone.now()
            or current.api_key.revoked_at
        ):
            return _token_error("invalid_grant")
        # Rotation: the old refresh token stops working the moment a new one is issued.
        return _issue(current)


def token_principal(raw):
    """(principal, api_key) for a valid access token, else None."""
    from .auth import APIKeyPrincipal

    if not raw.startswith(ACCESS_PREFIX) or len(raw) > 120:
        return None
    token = (
        OAuthToken.objects.select_related("api_key__workspace")
        .filter(access_hash=_hash(raw), revoked_at__isnull=True)
        .first()
    )
    if token is None or token.access_expires_at < timezone.now() or token.api_key.revoked_at:
        return None
    return APIKeyPrincipal(token.api_key), token.api_key
