from django.db import models
from pgvector.django import VectorField

from apps.tenants.crypto import EncryptedTextField
from apps.tenants.models import TenantModel


class AgentConfig(TenantModel):
    name = models.CharField(max_length=100, default="Sales assistant")
    system_prompt = models.TextField(
        default="Help customers using the supplied knowledge. Never invent prices or availability."
    )
    provider = models.CharField(max_length=20, default="openai")
    model = models.CharField(max_length=100, default="gpt-5.4-mini")
    api_key = EncryptedTextField(blank=True)
    embedding_model = models.CharField(max_length=100, default="text-embedding-3-small")
    # Knowledge-base vectors are always OpenAI embeddings. A BYO workspace whose chat
    # provider is not OpenAI supplies an OpenAI key here for its documents.
    embedding_api_key = EncryptedTextField(blank=True)
    # Optional second provider for rate limits and outages, on platform credits only
    # (a BYO key belongs to one vendor). Billed at the rate of the model that answered.
    fallback_provider = models.CharField(max_length=20, blank=True)
    fallback_model = models.CharField(max_length=100, blank=True)
    allowed_tools = models.JSONField(default=list)
    enabled = models.BooleanField(default=False)
    is_test = models.BooleanField(default=False)
    input_cost_per_million = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    output_cost_per_million = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    # Sales stage machine: fields the agent must collect before it may pitch.
    qualifying_fields = models.JSONField(default=list)
    segmentation_enabled = models.BooleanField(default=True)
    segmentation_prompt = models.TextField(blank=True, default="")
    # Triage: deterministic keyword handoff plus LLM sentiment/urgency classification.
    triage_enabled = models.BooleanField(default=True)
    handoff_keywords = models.JSONField(default=list)
    max_tool_rounds = models.PositiveSmallIntegerField(default=4)
    # Seconds to wait after a customer's last message before replying, so several quick
    # messages get one answer instead of one answer each. 0 replies at once.
    reply_delay_seconds = models.PositiveSmallIntegerField(default=0)
    # platform_credits: Instantlify's provider key, prepaid balance debited per call.
    # byo_key: the workspace's own key, nothing debited. Explicit per workspace (2.10).
    billing_mode = models.CharField(max_length=20, default="platform_credits")
    # agent: LangGraph sales agent with tools and stages. simple: one grounded
    # model call per message, no tools (see agents/simple.py).
    mode = models.CharField(max_length=10, default="agent")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_workspace_agent")]


class KnowledgeBase(TenantModel):
    """A named collection of documents an AI agent step can answer from. Documents
    without a base form the workspace's General knowledge."""

    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["created_at", "id"]


class KnowledgeDocument(TenantModel):
    knowledge_base = models.ForeignKey(
        KnowledgeBase, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents"
    )
    title = models.CharField(max_length=200)
    source = EncryptedTextField()
    source_revision = models.PositiveIntegerField(default=0)
    file_type = models.CharField(max_length=10, default="text")
    status = models.CharField(max_length=20, default="pending")
    error_code = models.CharField(max_length=50, blank=True)
    embedding_model = models.CharField(max_length=100, blank=True)


class KnowledgeChunk(TenantModel):
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE)
    position = models.PositiveIntegerField()
    text = EncryptedTextField()
    embedding = VectorField(dimensions=1536)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "position"], name="unique_document_chunk")
        ]


class KnowledgeSourceSync(TenantModel):
    integration = models.OneToOneField("crm.IntegrationConfig", on_delete=models.CASCADE)
    enabled = models.BooleanField(default=False)
    interval_minutes = models.PositiveIntegerField(default=60)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=20, default="idle")
    lease_token = models.UUIDField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=50, blank=True)


class AgentSession(TenantModel):
    conversation = models.OneToOneField("crm.Conversation", on_delete=models.CASCADE)
    stage = models.CharField(max_length=30, default="qualify")
    last_intent = models.CharField(max_length=30, blank=True)
    last_sentiment = models.CharField(max_length=20, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class AgentRun(TenantModel):
    message = models.OneToOneField("crm.Message", on_delete=models.CASCADE)
    status = models.CharField(max_length=30, default="pending")
    checkpoint = EncryptedTextField(default="{}")
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=50, blank=True)


class ToolCall(TenantModel):
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    input = EncryptedTextField()
    output = EncryptedTextField(default="{}")
    status = models.CharField(max_length=30, default="pending")
    confirmation_code = models.CharField(max_length=12, blank=True)
    expires_at = models.DateTimeField(null=True)


class UsageRecord(TenantModel):
    key = models.CharField(max_length=255)
    provider = models.CharField(max_length=20)
    model = models.CharField(max_length=100)
    kind = models.CharField(max_length=20, default="generation")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=16, decimal_places=8, default=0)
    status = models.CharField(max_length=20, default="reserved")
    reported_at = models.DateTimeField(null=True)
    report_attempts = models.PositiveIntegerField(default=0)
    report_after = models.DateTimeField(null=True)
    # Model calls aggregated into this record; each is its own credit ledger row.
    calls = models.PositiveIntegerField(default=0)
    billing_mode = models.CharField(max_length=20, blank=True)
    # Transcription is billed by audio length, not tokens; kept apart so token totals
    # on the console never mix in seconds.
    audio_seconds = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "key"], name="unique_usage_record")
        ]


class VoiceAsset(TenantModel):
    audio = EncryptedTextField()
    content_type = models.CharField(max_length=50, default="audio/mpeg")
