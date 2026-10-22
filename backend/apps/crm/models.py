from django.conf import settings
from django.db import models

from apps.tenants.crypto import EncryptedTextField
from apps.tenants.models import TenantModel


class Lead(TenantModel):
    name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    stage = models.CharField(max_length=20, default="new")
    tags = models.JSONField(default=list)
    fields = models.JSONField(default=dict)
    opted_out = models.BooleanField(default=False)
    # Public profile as the channel reports it: @username or phone, and a photo URL.
    handle = models.CharField(max_length=150, blank=True)
    avatar_url = models.URLField(max_length=1000, blank=True)
    profile_synced_at = models.DateTimeField(null=True, blank=True)
    # Set when a first message arrives; the enrichment worker fetches the profile.
    profile_due_at = models.DateTimeField(null=True, blank=True)
    # Debounced AI intent classification; set on inbound messages, cleared when claimed.
    segment_due_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["segment_due_at"]),
            models.Index(fields=["profile_due_at"]),
        ]


class ChannelIdentity(TenantModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE)
    connection = models.ForeignKey("channels.ChannelConnection", on_delete=models.CASCADE)
    external_id = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "external_id"], name="unique_channel_identity"
            )
        ]


class Conversation(TenantModel):
    identity = models.OneToOneField(ChannelIdentity, on_delete=models.CASCADE)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=20, default="open")
    ai_enabled = models.BooleanField(default=False)
    last_inbound_at = models.DateTimeField(null=True)
    last_outbound_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]


class Message(TenantModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    direction = models.CharField(max_length=10)
    text = EncryptedTextField(blank=True)
    kind = models.CharField(max_length=20, default="text")
    attachments = EncryptedTextField(default="[]")
    event = models.OneToOneField("channels.WebhookEvent", null=True, on_delete=models.SET_NULL)
    delivery = models.OneToOneField("channels.Delivery", null=True, on_delete=models.SET_NULL)
    # Teammate who wrote an outbound reply; null for customers, AI, flows and the API.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # "" (not a voice note), pending, processing, complete, failed.
    transcription_status = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["transcription_status"])]


class InternalNote(TenantModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    text = EncryptedTextField()

    class Meta:
        ordering = ["created_at", "id"]


class IntegrationConfig(TenantModel):
    provider = models.CharField(max_length=30)
    credentials = EncryptedTextField(default="{}")
    options = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)
    is_test = models.BooleanField(default=False)
    # active, reconnect_required (refresh/auth failed), disconnected (credentials removed).
    status = models.CharField(max_length=20, default="active")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "provider"], name="unique_workspace_integration"
            )
        ]


class IntegrationJob(TenantModel):
    integration = models.ForeignKey(IntegrationConfig, on_delete=models.CASCADE)
    operation = models.CharField(max_length=40)
    payload = EncryptedTextField()
    idempotency_key = models.CharField(max_length=255)
    status = models.CharField(max_length=20, default="pending")
    result = EncryptedTextField(default="{}")
    available_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "idempotency_key"], name="unique_integration_job"
            )
        ]
