from django.db import models

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
