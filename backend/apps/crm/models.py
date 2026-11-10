from django.conf import settings
from django.db import models, transaction
from django.db.models import Max

from apps.tenants.crypto import EncryptedTextField
from apps.tenants.models import TenantModel


class Lead(TenantModel):
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_contacts",
    )
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
    # Written on request by the workspace AI model from the contact's messages.
    ai_summary = models.TextField(blank=True)
    ai_summary_at = models.DateTimeField(null=True, blank=True)
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


class AssignmentNotification(TenantModel):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignment_notifications"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="sent_assignment_notifications",
    )
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["workspace", "recipient", "read_at"], name="assignment_unread_idx")
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
    handoff_reason = models.CharField(max_length=30, blank=True)
    last_inbound_at = models.DateTimeField(null=True)
    last_outbound_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]


class Message(TenantModel):
    # Serializes creation order when clocks give several messages the same timestamp.
    sequence = models.PositiveBigIntegerField(null=True, editable=False)
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
        ordering = ["created_at", "sequence", "id"]
        indexes = [models.Index(fields=["transcription_status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "sequence"], name="unique_conversation_message_sequence"
            )
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and self.sequence is None and self.conversation_id:
            from django.core.exceptions import ValidationError

            with transaction.atomic():
                conversation = (
                    Conversation.objects.for_workspace(self.workspace_id)
                    .select_for_update()
                    .filter(pk=self.conversation_id)
                    .first()
                )
                if conversation is None:
                    raise ValidationError("Related records must belong to this workspace.")
                previous = (
                    Message.objects.for_workspace(self.workspace_id)
                    .filter(conversation_id=self.conversation_id)
                    .aggregate(last=Max("sequence"))["last"]
                    or 0
                )
                self.sequence = previous + 1
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)


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
    form_submission = models.ForeignKey(
        "tools.FormSubmission", null=True, blank=True, on_delete=models.CASCADE
    )
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


class Campaign(TenantModel):
    name = models.CharField(max_length=100, default="New campaign")
    connection = models.ForeignKey(
        "channels.ChannelConnection", null=True, blank=True, on_delete=models.SET_NULL
    )
    text = EncryptedTextField(blank=True, default="")
    buttons = models.JSONField(default=list)
    media_url = models.URLField(max_length=2000, blank=True)
    media_type = models.CharField(max_length=10, default="image")
    tag = models.CharField(max_length=40, blank=True)
    audience = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="draft")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    launched_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    expected_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class ContactSegment(TenantModel):
    name = models.CharField(max_length=32)
    prompt = EncryptedTextField()
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "name"], name="unique_contact_segment")
        ]


class CampaignRecipient(TenantModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="recipients")
    conversation = models.ForeignKey(Conversation, null=True, on_delete=models.SET_NULL)
    lead = models.ForeignKey(Lead, null=True, on_delete=models.SET_NULL)
    text_delivery = models.ForeignKey(
        "channels.Delivery", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    media_delivery = models.ForeignKey(
        "channels.Delivery", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=20, default="pending")
    error_code = models.CharField(max_length=60, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "conversation"], name="one_campaign_recipient"
            )
        ]


class MessageAttachment(TenantModel):
    """A file a teammate sent from the inbox. Providers (Meta, Telegram) fetch media by
    URL, so the bytes are served from a signed link rather than a public bucket."""

    conversation = models.ForeignKey(
        "crm.Conversation", on_delete=models.CASCADE, related_name="attachments"
    )
    filename = models.CharField(max_length=200)
    content_type = models.CharField(max_length=60)
    size = models.PositiveIntegerField()
    data = EncryptedTextField()


class SavedReply(TenantModel):
    """A workspace-wide canned reply teammates insert from the inbox composer."""

    text = models.CharField(max_length=1000)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]
