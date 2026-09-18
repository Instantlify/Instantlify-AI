"""Escalation check that runs on every inbound message before any automation.

A keyword flow answering "I want a refund, this is a scam" with a canned pricing DM is
worse than silence. So before `route_message` can start or resume a flow, the message is
checked for escalation phrases; a hit hands the conversation to a human (flows stopped,
AI paused, team paged) and nothing automated replies.

Deliberately deterministic: this runs inside the ingest transaction while the
conversation row is locked, so it makes no provider call. Sentiment/urgency
classification by the model still happens inside the agent run, which hands off the
same way.
"""

from dataclasses import dataclass

# Phrases, not bare words: "agent" and "human" alone appear in ordinary business chat
# ("are you a travel agent?", "human resources"). "cancel" is left out because
# "cancel subscription" is the opt-out command, handled before triage.
DEFAULT_ESCALATION_PHRASES = [
    "speak to a human",
    "talk to a human",
    "real person",
    "your manager",
    "refund",
    "chargeback",
    "lawyer",
    "complaint",
    "scam",
    "fraud",
]


@dataclass(frozen=True)
class Triage:
    escalate: bool
    matched: str = ""


def escalation_phrases(workspace_id):
    """The workspace's own handoff keywords when it configured some, else the defaults.
    None means the workspace switched triage off."""
    from apps.agents.models import AgentConfig

    config = (
        AgentConfig.objects.for_workspace(workspace_id)
        .only("triage_enabled", "handoff_keywords")
        .first()
    )
    if config and not config.triage_enabled:
        return None
    return (config.handoff_keywords if config else None) or DEFAULT_ESCALATION_PHRASES


def triage_inbound(message):
    from apps.automations.services import keyword_matches

    text = message.text.strip()
    phrases = escalation_phrases(message.workspace_id)
    if not text or not phrases:
        return Triage(False)
    # Whole-word matching, so "refundable" or "scampi" never page anyone.
    for phrase in phrases:
        if phrase.strip() and keyword_matches(phrase.strip(), text):
            return Triage(True, phrase.strip())
    return Triage(False)
