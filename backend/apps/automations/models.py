import uuid

from django.db import models

from apps.tenants.crypto import EncryptedTextField
from apps.tenants.models import TenantModel


class Automation(TenantModel):
    name = models.CharField(max_length=100)
    draft = models.JSONField(default=dict)
    published = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    # Marketplace template this automation was installed from, if any (no FK: other tenant).
    installed_from = models.UUIDField(null=True, blank=True)
    # Free-form grouping for the folders view; blank means unfiled.
    folder = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["-updated_at", "id"]


class Trigger(TenantModel):
    automation = models.ForeignKey(Automation, on_delete=models.CASCADE)
    kind = models.CharField(max_length=20)
    keyword = models.CharField(max_length=100)
    # Provider this trigger listens on; blank matches every connected channel.
    channel = models.CharField(max_length=30, blank=True)
    # "keyword": `keyword` must appear in the message. "intent": `keyword` describes what
    # the message means (e.g. "asks about price") and the workspace model decides.
    match = models.CharField(max_length=10, default="keyword")


class Node(TenantModel):
    automation = models.ForeignKey(Automation, on_delete=models.CASCADE)
    node_id = models.CharField(max_length=80)
    kind = models.CharField(max_length=30)
    config = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["automation", "node_id"], name="unique_automation_node")
        ]


class Edge(TenantModel):
    automation = models.ForeignKey(Automation, on_delete=models.CASCADE)
    source = models.CharField(max_length=80)
    target = models.CharField(max_length=80)
    branch = models.CharField(max_length=10, blank=True)


class ConversationState(TenantModel):
    run_token = models.UUIDField(default=uuid.uuid4)
    conversation = models.OneToOneField("crm.Conversation", on_delete=models.CASCADE)
    automation = models.ForeignKey(Automation, on_delete=models.CASCADE)
    graph = models.JSONField(default=dict)
    node_id = models.CharField(max_length=80)
    variables = models.JSONField(default=dict)
    steps = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, default="running")
    available_at = models.DateTimeField()
    last_message_id = models.UUIDField(null=True)
    cooldown_until = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=50, blank=True)
    experiment_id = models.UUIDField(null=True)
    variant = models.CharField(max_length=10, blank=True)
    # When a waiting step gives up on a reply and takes its "timeout" path.
    timeout_at = models.DateTimeField(null=True, blank=True, db_index=True)

    def save(self, *args, **kwargs):
        from django.db import transaction

        from .history import record_state

        with transaction.atomic():
            super().save(*args, **kwargs)
            record_state(self)


class AutomationExecution(TenantModel):
    """A run survives the mutable conversation cursor and automation transfers."""

    conversation = models.ForeignKey("crm.Conversation", on_delete=models.CASCADE)
    automation_id = models.UUIDField()
    automation_name = models.CharField(max_length=100)
    revision = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20)
    steps = models.PositiveIntegerField(default=0)
    node_id = models.CharField(max_length=80)
    error_code = models.CharField(max_length=60, blank=True)
    trace = models.JSONField(default=list)
    finished_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class WorkflowLink(TenantModel):
    state = models.ForeignKey(ConversationState, null=True, on_delete=models.SET_NULL)
    conversation = models.ForeignKey("crm.Conversation", on_delete=models.CASCADE)
    run_token = models.UUIDField()
    source_node = models.CharField(max_length=80)
    key = models.CharField(max_length=255)
    code = models.CharField(max_length=48, unique=True)
    target = EncryptedTextField()
    automation_id = models.UUIDField(null=True)
    experiment_id = models.UUIDField(null=True)
    variant = models.CharField(max_length=10, blank=True)
    clicked_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "key"], name="unique_workflow_link")
        ]
        indexes = [models.Index(fields=["workspace", "run_token", "source_node"])]


class WorkflowActionJob(TenantModel):
    state = models.ForeignKey(ConversationState, on_delete=models.CASCADE)
    kind = models.CharField(max_length=30)
    key = models.CharField(max_length=255)
    payload = EncryptedTextField(default="{}")
    result = EncryptedTextField(default="{}")
    status = models.CharField(max_length=20, default="pending")
    available_at = models.DateTimeField()
    error_code = models.CharField(max_length=60, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "key"], name="unique_workflow_action_job")
        ]


class AutomationTransferLog(models.Model):
    """Every move of an automation between workspaces. Deliberately not a TenantModel:
    the row describes two tenants, and it must survive either workspace being deleted."""

    automation_id = models.UUIDField()
    automation_name = models.CharField(max_length=100)
    from_workspace = models.ForeignKey(
        "tenants.Workspace", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    to_workspace = models.ForeignKey(
        "tenants.Workspace", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    operator = models.ForeignKey("tenants.User", null=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class IntentMatch(TenantModel):
    """A message waiting for the model to decide which intent trigger (if any) it fits."""

    message = models.OneToOneField("crm.Message", on_delete=models.CASCADE)
    payload = models.JSONField(default=dict)
    candidates = models.JSONField(default=list)
    status = models.CharField(max_length=20, default="pending")
    trigger_id = models.UUIDField(null=True, blank=True)
    error_code = models.CharField(max_length=60, blank=True)
    available_at = models.DateTimeField()
