"""Comment shield: match inbound comments against the workspace's rules and act."""

import logging

from .models import ShieldEvent, ShieldRule

log = logging.getLogger(__name__)

# Rule actions that stop the comment from starting any automation.
SILENCING = {"hide", "delete"}


def matching_rule(workspace_id, text):
    haystack = (text or "").lower()
    if not haystack:
        return None
    for rule in ShieldRule.objects.for_workspace(workspace_id).filter(enabled=True):
        if any(
            isinstance(keyword, str) and keyword.strip() and keyword.strip().lower() in haystack
            for keyword in rule.keywords
        ):
            return rule
    return None


def moderate_comment(message, payload):
    """Record the first matching rule for a comment and apply its action through the
    channel adapter. Returns True when the comment must not reach automations."""
    rule = matching_rule(message.workspace_id, message.text)
    if not rule:
        return False
    connection = message.conversation.identity.connection
    comment_id = str(payload.get("comment_id") or "")
    taken = "flagged"
    if rule.action in SILENCING and comment_id:
        from apps.channels.adapters import adapter_for

        try:
            adapter = adapter_for(connection)
            if rule.action == "delete":
                adapter.delete_comment(comment_id)
                taken = "deleted"
            else:
                adapter.hide_comment(comment_id)
                taken = "hidden"
        except Exception as exc:  # noqa: BLE001 - moderation must never break ingress
            log.warning("comment shield could not %s %s: %s", rule.action, comment_id, exc)
            taken = "failed"
    ShieldEvent.objects.for_workspace(message.workspace_id).create(
        workspace_id=message.workspace_id,
        rule=rule,
        rule_name=rule.name,
        connection=connection,
        comment_id=comment_id,
        author=str(payload.get("sender_id") or "")[:150],
        text=(message.text or "")[:2000],
        action_taken=taken,
    )
    return rule.action in SILENCING
