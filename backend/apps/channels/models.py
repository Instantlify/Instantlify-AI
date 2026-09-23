from django.conf import settings
from django.db import models

from apps.tenants.crypto import EncryptedTextField
from apps.tenants.models import TenantModel


class ChannelConnection(TenantModel):
    provider = models.CharField(max_length=30, default="instagram")
    external_account_id = models.CharField(max_length=200)
    display_name = models.CharField(max_length=150)
    access_token = EncryptedTextField()
    expires_at = models.DateTimeField()
    is_test = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="active")
    # Public profile facts (biography, website, follower count) as the provider
    # returns them. Read by segment classification, which re-runs on every
    # reconnect because a bio changes.
    profile = models.JSONField(default=dict, blank=True)
    webhook_secret = EncryptedTextField(blank=True)
    last_refreshed_at = models.DateTimeField(null=True)
    refresh_due_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_account_id"], name="unique_provider_account"
            )
        ]
        ordering = ["created_at", "id"]


class OAuthState(TenantModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Which hosted sign-in this state belongs to; a callback only accepts its own.
    provider = models.CharField(max_length=30, default="instagram")
    state_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)


class WebhookEvent(TenantModel):
    connection = models.ForeignKey(ChannelConnection, on_delete=models.CASCADE)
    event_id = models.CharField(max_length=255)
    payload = EncryptedTextField()
    status = models.CharField(max_length=20, default="pending")
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField()
    processed_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=50, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["connection", "event_id"], name="unique_channel_event")
        ]
        indexes = [models.Index(fields=["status", "available_at"])]


class Delivery(TenantModel):
    connection = models.ForeignKey(ChannelConnection, on_delete=models.CASCADE)
    recipient_id = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=255)
    payload = EncryptedTextField()
    status = models.CharField(max_length=20, default="pending")
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    error_code = models.CharField(max_length=50, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "idempotency_key"], name="unique_delivery_intent"
            )
        ]
        indexes = [models.Index(fields=["status", "available_at"])]
