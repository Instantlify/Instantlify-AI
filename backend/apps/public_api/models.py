import uuid

from django.conf import settings
from django.db import models

from apps.tenants.crypto import EncryptedTextField
from apps.tenants.models import TenantModel

SCOPES = ["read", "write"]

EVENTS = [
    "form.submitted",
    "lead.created",
    "lead.updated",
    "lead.hot",
    "message.received",
    "message.sent",
    "conversation.handoff",
    "call.booked",
    "payment.paid",
]


class APIKey(TenantModel):
    """Workspace-scoped bearer credential for the public API. Only a hash is stored."""

    name = models.CharField(max_length=80)
    prefix = models.CharField(max_length=12)
    key_hash = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    last_used_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class WebhookSubscription(TenantModel):
    """REST-hook style subscription (Zapier/n8n/Make). Payloads are signed with `secret`."""

    url = models.URLField(max_length=2000)
    events = models.JSONField(default=list)
    secret = EncryptedTextField()
    # Shared token sent as X-Instantlify-Token for receivers that cannot compute an HMAC
    # (e.g. Make). Weaker than the signature: no body integrity or replay protection
    # beyond TLS, so it is a second header, never a replacement.
    token = EncryptedTextField(blank=True)
    active = models.BooleanField(default=True)
    api_key = models.ForeignKey(APIKey, null=True, on_delete=models.SET_NULL)
    failure_count = models.PositiveIntegerField(default=0)
    last_delivered_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class OutboundWebhook(TenantModel):
    subscription = models.ForeignKey(WebhookSubscription, on_delete=models.CASCADE)
    event = models.CharField(max_length=40)
    payload = EncryptedTextField()
    status = models.CharField(max_length=20, default="pending")
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField()
    response_code = models.PositiveSmallIntegerField(null=True)
    delivered_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [models.Index(fields=["status", "available_at"])]


class MCPClient(TenantModel):
    """An MCP client (Claude Desktop, Claude Code, an agent) that has initialized a
    session with a workspace API key. One row per key and client name; `last_active_at`
    moves on every request, so "connected" means recently used, not merely configured."""

    api_key = models.ForeignKey(APIKey, on_delete=models.CASCADE)
    client_name = models.CharField(max_length=100)
    client_version = models.CharField(max_length=50, blank=True)
    protocol_version = models.CharField(max_length=20, blank=True)
    last_active_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["api_key", "client_name"], name="one_mcp_client_per_key"
            )
        ]


class OAuthClient(models.Model):
    """An MCP client registered itself through dynamic client registration (RFC 7591).
    Public client: no secret, PKCE required."""

    client_id = models.CharField(max_length=64, unique=True)
    client_name = models.CharField(max_length=100)
    redirect_uris = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class OAuthAuthorization(models.Model):
    """One authorization request, from the authorize redirect through user consent to
    the code exchange. Only a hash of the code is stored."""

    # Random, so a pending request cannot be guessed and approved by someone else.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    client = models.ForeignKey(OAuthClient, on_delete=models.CASCADE)
    redirect_uri = models.CharField(max_length=2000)
    code_challenge = models.CharField(max_length=128)
    state = models.CharField(max_length=500, blank=True)
    scopes = models.JSONField(default=list)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE)
    workspace = models.ForeignKey("tenants.Workspace", null=True, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(max_length=10, default="pending")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class OAuthToken(models.Model):
    """Access and refresh token pair. Each grant is backed by a workspace API key, so
    MCP tools, throttles and auditing treat OAuth and key callers the same, and revoking
    that key in Instantlify ends the connection."""

    client = models.ForeignKey(OAuthClient, on_delete=models.CASCADE)
    authorization = models.ForeignKey(OAuthAuthorization, null=True, on_delete=models.SET_NULL)
    api_key = models.ForeignKey(APIKey, on_delete=models.CASCADE)
    access_hash = models.CharField(max_length=64, unique=True)
    refresh_hash = models.CharField(max_length=64, unique=True)
    access_expires_at = models.DateTimeField()
    refresh_expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
