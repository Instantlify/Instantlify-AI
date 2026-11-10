"""Instantlify's own support agent — the bot on our marketing site and in-app widget.

Distinct from `apps.agents` in every way that matters: it answers questions about
Instantlify to our prospects, it is grounded in `PlatformKnowledgeSection` (never a
tenant's documents), it runs on the platform key, and it is not billed to anyone's
credit balance.

Ticket creation is gated on having both a name and an email. The system prompt says
so, but the prompt is not the enforcement: `open_ticket` here refuses without both,
because a model can be talked out of an instruction and a function signature cannot.
"""

from .growth import open_ticket
from .intelligence import complete, retrieve_sections
from .models import PlatformSetting

NAME_CARD = "[[REQUEST_NAME_CARD]]"
EMAIL_CARD = "[[REQUEST_EMAIL_CARD]]"
SENTINELS = [NAME_CARD, EMAIL_CARD]

DEFAULT_PROMPT = """You are Instantlify's support assistant. Answer questions about Instantlify
using only the knowledge sections provided. If the knowledge does not cover it, say
so plainly and offer to open a ticket rather than guessing.

## Ticket creation

Before opening a ticket you must have BOTH the person's name AND their email.

1. If the name is missing, your ENTIRE response must be exactly: [[REQUEST_NAME_CARD]]
2. If the name is known but the email is missing, your ENTIRE response must be
   exactly: [[REQUEST_EMAIL_CARD]]
3. Only once you have both may a ticket be opened.

Never ask for a name or an email in prose — the card tokens render a proper input
field, and a typed answer in prose cannot be parsed reliably. Never combine a card
token with any other text. Never open a ticket without both details.

Choose the category: "billing" for payment, subscription, plan or refund issues;
"bug" for something broken or erroring; "support" for everything else.
"""


def system_prompt():
    return PlatformSetting.get("support_agent_system_prompt", "") or DEFAULT_PROMPT


def grounding(question):
    sections = retrieve_sections(question)
    if not sections:
        return "", []
    text = "\n\n".join(
        f"## {section.document.title} — {section.title}\n{section.body_markdown}"
        for section in sections
    )
    return text, [f"{section.document.title}: {section.title}" for section in sections]


def next_card(*, name, email):
    """The gate, in code. Returns the sentinel the client should render, or None when
    both details are in hand."""
    if not (name or "").strip():
        return NAME_CARD
    if not (email or "").strip():
        return EMAIL_CARD
    return None


def answer(question, *, name="", email="", wants_ticket=False):
    """One turn of the support conversation.

    When the person is asking for a ticket, the missing-detail card is returned
    directly rather than asked for by the model — the model is free to be talked out
    of an instruction, and this path must not be.
    """
    question = (question or "").strip()
    if not question:
        return {"reply": "What can I help you with?", "sentinel": None, "sources": []}
    if wants_ticket:
        card = next_card(name=name, email=email)
        if card:
            return {"reply": card, "sentinel": card, "sources": []}
    knowledge, sources = grounding(question)
    prompt = system_prompt()
    if knowledge:
        prompt += "\n\n# Knowledge\n" + knowledge
    reply = (complete(prompt, question) or "").strip()
    # A model that emits a card token alongside other text has broken the contract;
    # honour the token and drop the rest rather than rendering a half-card.
    for sentinel in SENTINELS:
        if sentinel in reply:
            return {"reply": sentinel, "sentinel": sentinel, "sources": []}
    return {"reply": reply, "sentinel": None, "sources": sources}


def create_ticket(*, name, email, subject, body="", category="support", channel="web-chat"):
    """The agent's only side-effecting tool. Refuses on missing details regardless of
    what the model believes it was told."""
    card = next_card(name=name, email=email)
    if card:
        return {"ok": False, "sentinel": card}
    ticket = open_ticket(
        subject=subject,
        body=body,
        category=category if category in {"billing", "bug", "support"} else "support",
        reporter_name=name,
        reporter_email=email,
        reporter_channel=channel,
        by_agent=True,
    )
    return {"ok": True, "ticket_number": ticket.ticket_number}
