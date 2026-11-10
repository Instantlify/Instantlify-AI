"""Comment shield: match inbound comments against the workspace's rules and act."""

import logging

from .models import ShieldEvent, ShieldRule

log = logging.getLogger(__name__)

# Rule actions that stop the comment from starting any automation.
SILENCING = {"hide", "delete"}


def matching_rule(workspace_id, text):
    """First enabled keyword rule the text contains."""
    haystack = (text or "").lower()
    if not haystack:
        return None
    for rule in ShieldRule.objects.for_workspace(workspace_id).filter(enabled=True, prompt=""):
        if any(
            isinstance(keyword, str) and keyword.strip() and keyword.strip().lower() in haystack
            for keyword in rule.keywords
        ):
            return rule
    return None


def ai_rule(message):
    """The AI rule the workspace model says this comment breaks, or None. Metered like
    any AI call. Any failure (no AI setup, no credits, bad answer) leaves the comment
    alone: moderation must never remove a comment it is unsure about."""
    rules = list(
        ShieldRule.objects.for_workspace(message.workspace_id)
        .filter(enabled=True)
        .exclude(prompt="")[:20]
    )
    if not rules or not (message.text or "").strip():
        return None
    try:
        from apps.automations.ai_steps import model_config
        from apps.automations.intents import classify, parse_choice
        from apps.billing.gating import check_feature
        from apps.billing.services import complete_usage, reserve_usage

        config = model_config(message.workspace_id, {})
        check_feature(message.workspace_id, "ai_agent_enabled")
        usage = reserve_usage(config, f"shield:{message.pk}", kind="moderation")
        completion = classify(
            config, message.text, [f"a comment that is {rule.prompt}" for rule in rules]
        )
        complete_usage(usage, completion, config)
        if completion.calls or not isinstance(completion.text, str):
            return None
        index = parse_choice(completion.text, len(rules))
    except Exception as exc:  # noqa: BLE001 - fail open, never break ingress
        log.warning("comment shield AI check skipped for %s: %s", message.pk, exc)
        return None
    return rules[index] if index is not None else None


def moderate_comment(message, payload):
    """Record the first matching rule for a comment and apply its action through the
    channel adapter. Returns True when the comment must not reach automations."""
    rule = matching_rule(message.workspace_id, message.text) or ai_rule(message)
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
    if rule.reply_text and rule.action != "delete" and comment_id:
        from apps.channels.adapters import adapter_for

        try:
            adapter_for(connection).reply_comment(
                comment_id=comment_id,
                text=rule.reply_text,
                idempotency_key=f"shield-reply:{message.pk}",
            )
            taken += "+replied"
        except Exception as exc:  # noqa: BLE001
            log.warning("comment shield could not reply to %s: %s", comment_id, exc)
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
