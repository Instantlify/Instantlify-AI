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
    # Shared token sent as X-Nemio-Token for receivers that cannot compute an HMAC
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
