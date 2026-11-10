import re
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.tenants.services import audit

from .models import Automation, ConversationState, Edge, Node, Trigger

# Longest a delay or a reply timeout may wait: 30 days.
MAX_WAIT_SECONDS = 30 * 24 * 3600

KINDS = {
    "ai_agent",
    "avatar_video",
    "ai_call",
    "generate_voice",
    "follow_gate",
    "send_reminder",
    "ai_generate",
    "ai_extract",
    "ai_condition",
    "send_media",
    "send_message",
    "send_buttons",
    "delay",
    "condition",
    "branch",
    "wait",
    "end",
    "capture_email",
    "add_tag",
    "assign_member",
    "transfer",
    "set_field",
    "set_stage",
    "randomizer",
    "integration_action",
    "start_agent",
}


def validate_graph(graph):
    if (
        not isinstance(graph, dict)
        or not isinstance(graph.get("nodes"), list)
        or not isinstance(graph.get("edges"), list)
    ):
        raise ValidationError("Graph must contain nodes and edges.")
    if not 1 <= len(graph["nodes"]) <= 100 or len(graph["edges"]) > 200:
        raise ValidationError("A flow must have 1–100 nodes and at most 200 edges.")
    nodes = {n.get("id"): n for n in graph["nodes"] if isinstance(n, dict)}
    if len(nodes) != len(graph["nodes"]) or any(
        not isinstance(key, str) or not re.fullmatch(r"[\w-]{1,80}", key) for key in nodes
    ):
        raise ValidationError("Node IDs must be unique and valid.")
    if graph.get("start") not in nodes:
        raise ValidationError("Select a valid start node.")
    for node in nodes.values():
        data = node.get("data", {})
        if not isinstance(data, dict):
            raise ValidationError("Node settings must be an object.")
        kind = data.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            raise ValidationError("Unsupported node type.")
        if kind in {"send_message", "send_buttons", "send_reminder"} and (
            not isinstance(data.get("text"), str) or not 1 <= len(data["text"]) <= 2000
        ):
            raise ValidationError("Message nodes require 1–2000 characters.")
        if kind == "send_buttons":
            buttons = data.get("buttons", [])
            if not isinstance(buttons, list) or not 1 <= len(buttons) <= 3:
                raise ValidationError("Use 1–3 buttons.")
            for button in buttons:
                if (
                    not isinstance(button, dict)
                    or not isinstance(button.get("title"), str)
                    or not 1 <= len(button["title"]) <= 20
                ):
                    raise ValidationError("Buttons need a title up to 20 characters.")
                if button.get("type") == "postback":
                    if (
                        not isinstance(button.get("payload"), str)
                        or not 1 <= len(button["payload"].encode()) <= 64
                    ):
                        raise ValidationError(
                            "Reply buttons need a response payload up to 64 bytes."
                        )
                elif (
                    button.get("type") != "web_url"
                    or not isinstance(button.get("url"), str)
                    or not button["url"].startswith("https://")
                ):
                    raise ValidationError(
                        "Buttons require an HTTPS URL and a title up to 20 characters."
                    )
                if button.get("type") == "web_url":
                    try:
                        url = urlsplit(button["url"])
                        valid = (
                            bool(url.hostname)
                            and not url.username
                            and not url.password
                            and len(button["url"]) <= 2000
                        )
                    except ValueError:
                        valid = False
                    if not valid:
                        raise ValidationError(
                            "Use a complete HTTPS resource URL without credentials."
                        )
        from .guided import validate_action

        validate_action(data)
        if kind == "ai_agent":
            from .agent_step import validate_agent

            validate_agent(data)
        if kind == "delay":
            validate_delay(data)
        if kind in {"condition", "branch"}:
            from .conditions import validate_condition

            validate_condition(data)
        if kind == "wait" and "timeout_seconds" in data:
            timeout = data["timeout_seconds"]
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, int)
                or not 60 <= timeout <= MAX_WAIT_SECONDS
            ):
                raise ValidationError("A reply timeout must be between 1 minute and 30 days.")
    for edge in graph["edges"]:
        if (
            not isinstance(edge, dict)
            or edge.get("source") not in nodes
            or edge.get("target") not in nodes
        ):
            raise ValidationError("Every edge must connect existing nodes.")
    for node_id, node in nodes.items():
        outgoing = [e for e in graph["edges"] if e["source"] == node_id]
        kind = node["data"]["kind"]
        if kind in {"condition", "branch", "randomizer", "ai_condition"}:
            if sorted(e.get("sourceHandle", "") for e in outgoing) != ["false", "true"]:
                raise ValidationError("Conditions need exactly one true and one false edge.")
        elif kind == "wait" and node["data"].get("timeout_seconds"):
            if sorted(e.get("sourceHandle", "") for e in outgoing) != ["", "timeout"]:
                raise ValidationError(
                    "A wait with a timeout needs one reply path and one timeout path."
                )
        elif len(outgoing) != (0 if kind in {"end", "transfer", "start_agent"} else 1):
            raise ValidationError("Each non-end node needs one outgoing edge.")
    visited = set()

    def visit(node_id, stack):
        if node_id in stack:
            raise ValidationError("Cycles are not allowed. Use a wait node for a reply.")
        if node_id in visited:
            return
        visited.add(node_id)
        for edge in graph["edges"]:
            if edge["source"] == node_id:
                visit(edge["target"], stack | {node_id})

    visit(graph["start"], set())
    if visited != set(nodes):
        raise ValidationError("Remove unreachable nodes.")
    triggers = graph.get("triggers", [])
    if not isinstance(triggers, list) or not triggers or len(triggers) > 20:
        raise ValidationError("Set 1–20 keyword triggers.")
    for trigger in triggers:
        if (
            not isinstance(trigger, dict)
            or not isinstance(trigger.get("kind"), str)
            or trigger["kind"] not in TRIGGER_CHANNELS
            or not isinstance(trigger.get("keyword"), str)
            or not 1 <= len(trigger["keyword"]) <= 100
        ):
            raise ValidationError("Invalid trigger.")
        match = trigger.get("match", "keyword")
        if match not in {"keyword", "intent"}:
            raise ValidationError("A trigger matches by keyword or by intent.")
        if match == "intent" and (
            trigger["keyword"] == ANY_KEYWORD or len(trigger["keyword"].strip()) < 3
        ):
            raise ValidationError("Describe the intent in 3–100 characters, e.g. asks about price.")
        channel = trigger.get("channel") or ""
        if not isinstance(channel, str) or (
            channel and channel not in TRIGGER_CHANNELS[trigger["kind"]]
        ):
            raise ValidationError("That trigger is not available on the chosen channel.")
    if any(not trigger.get("channel") or trigger["channel"] == "whatsapp" for trigger in triggers):
        for node in nodes.values():
            data = node["data"]
            if data["kind"] != "send_buttons":
                continue
            rendered = data["text"]
            links = [b for b in data["buttons"] if b["type"] == "web_url"]
            if links:
                rendered += "\n\n" + "\n".join(f"{b['title']}: {b['url']}" for b in links)
            limit = 1024 if any(b["type"] == "postback" for b in data["buttons"]) else 4096
            if len(rendered) > limit:
                raise ValidationError(
                    f"This WhatsApp message must fit {limit} characters including links."
                )
    from apps.channels.commenting import validate_comment_settings

    validate_comment_settings(graph)
    from apps.channels.media import validate_media_channels

    validate_media_channels(graph)
    from .tracking import validate_tracking

    validate_tracking(graph)
    from .followers import validate_followers

    validate_followers(graph)
    return graph


def validate_delay(data):
    def seconds(value):
        if isinstance(value, bool):
            raise ValueError
        return int(value)

    try:
        low = seconds(data.get("seconds", 0))
        high = seconds(data["seconds_max"]) if data.get("seconds_max") else None
    except (TypeError, ValueError):
        raise ValidationError("Delays must be a whole number of seconds.") from None
    if not 1 <= low <= MAX_WAIT_SECONDS:
        raise ValidationError("Delays must be between 1 second and 30 days.")
    if high is not None and not low < high <= MAX_WAIT_SECONDS:
        raise ValidationError(
            "A random delay needs a maximum above its minimum and at most 30 days."
        )


def delay_seconds(state, data):
    """Fixed delay, or a deterministic pick inside a random window so a retried step
    waits the same time."""
    low = int(data["seconds"])
    high = int(data.get("seconds_max") or 0)
    if high <= low:
        return low
    import hashlib

    seed = f"{state.run_token}:{state.node_id}:{state.steps}"
    return low + int(hashlib.sha256(seed.encode()).hexdigest(), 16) % (high - low + 1)


# Channels each trigger kind can arrive on; a blank channel on a trigger means "any".
TRIGGER_CHANNELS = {
    "dm": {"instagram", "messenger", "whatsapp", "telegram", "linkedin", "webchat"},
    "comment": {"instagram", "messenger", "linkedin"},
    "story_reply": {"instagram"},
    "live_comment": {"instagram"},
}


@transaction.atomic
def publish(automation, graph, actor):
    graph = validate_graph(graph)
    from .guided import validate_workspace_references

    validate_workspace_references(graph, automation.workspace_id, automation.pk)
    graph = dict(graph)
    graph.pop("resolved_next_post_id", None)
    graph.pop("comment_since", None)
    if graph.get("comment_post_mode") == "next":
        graph["comment_since"] = timezone.now().isoformat()
    automation = (
        Automation.objects.for_workspace(automation.workspace_id)
        .select_for_update()
        .get(pk=automation.pk)
    )
    for model in [Node, Edge, Trigger]:
        model.objects.for_workspace(automation.workspace_id).filter(automation=automation).delete()
    for node in graph["nodes"]:
        Node.objects.for_workspace(automation.workspace_id).create(
            workspace_id=automation.workspace_id,
            automation=automation,
            node_id=node["id"],
            kind=node["data"]["kind"],
            config=node["data"],
        )
    for edge in graph["edges"]:
        Edge.objects.for_workspace(automation.workspace_id).create(
            workspace_id=automation.workspace_id,
            automation=automation,
            source=edge["source"],
            target=edge["target"],
            branch=edge.get("sourceHandle", ""),
        )
    for trigger in graph["triggers"]:
        Trigger.objects.for_workspace(automation.workspace_id).create(
            workspace_id=automation.workspace_id,
            automation=automation,
            kind=trigger["kind"],
            keyword=trigger["keyword"],
            channel=trigger.get("channel") or "",
            match=trigger.get("match", "keyword"),
        )
    automation.published = graph
    automation.draft = graph
    automation.revision += 1
    automation.enabled = True
    automation.save()
    audit(automation.workspace, actor, "automation.published", automation.id)
    return automation


# A trigger with this keyword fires on every message of its kind and channel.
ANY_KEYWORD = "*"


def keyword_matches(keyword, text):
    return (
        re.search(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", text, flags=re.IGNORECASE)
        is not None
    )


def start_flow(conversation, automation, *, message, comment_id=None, experiment=None, variant=""):
    """Run `automation`'s published graph on this conversation from its start node.
    `message` is the inbound message the flow answers (its text seeds `last_text`)."""
    from .models import AutomationExecution

    graph = automation.published
    AutomationExecution.objects.for_workspace(conversation.workspace_id).filter(
        conversation=conversation, status__in=["running", "waiting"]
    ).update(status="superseded", finished_at=timezone.now())
    return ConversationState.objects.for_workspace(conversation.workspace_id).update_or_create(
        conversation=conversation,
        defaults={
            "workspace_id": conversation.workspace_id,
            "run_token": uuid.uuid4(),
            "automation": automation,
            "graph": graph,
            "node_id": graph["start"],
            "status": "running",
            "error_code": "",
            "steps": 0,
            "variables": {"last_text": message.text if message else "", "comment_id": comment_id},
            "available_at": timezone.now(),
            "last_message_id": message.id if message else None,
            "cooldown_until": timezone.now() + timedelta(hours=1),
            "experiment_id": experiment.pk if experiment else None,
            "variant": variant,
        },
    )[0]


def route_message(message, payload):
    state = (
        ConversationState.objects.for_workspace(message.workspace_id)
        .select_for_update()
        .filter(conversation=message.conversation)
        .first()
    )
    if state and state.status == "waiting":
        node = next(n for n in state.graph["nodes"] if n["id"] == state.node_id)
        data = node["data"]
        if data["kind"] == "ai_agent":
            # The agent answers private messages only; it stays on its step until done.
            if payload.get("kind", "dm") != "dm":
                return
            state.variables["last_text"] = message.text
            state.status = "running"
            state.available_at = timezone.now()
            state.last_message_id = message.id
            state.save()
            return
        # Guided opt-in and email capture only resume on private replies, never comments.
        if (data.get("expected_reply") or data["kind"] == "capture_email") and payload.get(
            "kind", "dm"
        ) != "dm":
            return
        if data.get("expected_reply") and message.text != data["expected_reply"]:
            return
        if data["kind"] == "capture_email":
            from .guided import capture_email

            if not capture_email(state, message, data):
                return
        state.variables[node["data"].get("variable", "reply")] = message.text
        state.variables["last_text"] = message.text
        if data["kind"] != "follow_gate":
            # A wait with a timeout also has a "timeout" path; a reply takes the other.
            state.node_id = next(
                e["target"]
                for e in state.graph["edges"]
                if e["source"] == state.node_id and e.get("sourceHandle", "") != "timeout"
            )
        state.timeout_at = None
        state.status = "running"
        state.available_at = timezone.now()
        state.last_message_id = message.id
        state.save()
        return
    if state and state.status == "running":
        # A flow is mid-step; neither triggers nor the agent may interleave.
        return
    # Cooldown only stops a flow from re-triggering; the agent may still answer.
    cooling = bool(state and state.cooldown_until and state.cooldown_until > timezone.now())
    provider = message.conversation.identity.connection.provider
    for trigger in (
        []
        if cooling
        else Trigger.objects.for_workspace(message.workspace_id)
        .filter(automation__enabled=True, kind=payload.get("kind", "dm"), match="keyword")
        .filter(Q(channel="") | Q(channel=provider))
        .select_related("automation")
        .order_by("created_at", "id")
    ):
        bound_connection = trigger.automation.published.get("connection_id")
        if bound_connection and str(bound_connection) != str(
            message.conversation.identity.connection_id
        ):
            continue
        if trigger.keyword == ANY_KEYWORD or keyword_matches(trigger.keyword, message.text):
            if fire_trigger(message, payload, trigger):
                return
    if not cooling:
        from .intents import queue_intent_match

        # Intent matching decides between a flow and the agent once the model answers.
        if queue_intent_match(message, payload):
            return
    queue_agent(message)


def fire_trigger(message, payload, trigger):
    """Start the trigger's automation (or its A/B arm) for this message. False when the
    chosen arm does not apply to this account or post."""
    from apps.analytics.services import choose_automation, record
    from apps.channels.commenting import matches_comment_target, queue_public_reply

    lead_id = message.conversation.identity.lead_id
    automation, experiment, arm = choose_automation(trigger.automation, lead_id)
    # An experiment arm must obey its own account and post constraints too.
    if automation.published.get("connection_id") and str(
        automation.published["connection_id"]
    ) != str(message.conversation.identity.connection_id):
        return False
    if not matches_comment_target(automation, message, payload):
        return False
    queue_public_reply(message, payload, automation)
    start_flow(
        message.conversation,
        automation,
        message=message,
        comment_id=payload.get("comment_id"),
        experiment=experiment,
        variant=arm,
    )
    record(
        message.workspace_id,
        "triggered",
        key=f"triggered:{message.id}",
        provider=message.conversation.identity.connection.provider,
        lead_id=lead_id,
        conversation_id=message.conversation_id,
        automation_id=automation.pk,
        experiment_id=experiment.pk if experiment else None,
        variant=arm,
    )
    return True


def queue_agent(message):
    if message.conversation.ai_enabled:
        from apps.agents.models import AgentRun

        run, created = AgentRun.objects.for_workspace(message.workspace_id).get_or_create(
            message=message, defaults={"workspace_id": message.workspace_id}
        )
        if created:
            audit(message.conversation.workspace, None, "agent.run_queued", run.id)


def in_experiment(automation):
    """Whether any A/B experiment uses this automation as an arm. Queried through the
    tenant manager: the reverse relations use the default manager, which fails closed
    and would always answer no."""
    from apps.analytics.models import Experiment

    return (
        Experiment.objects.for_workspace(automation.workspace_id)
        .filter(Q(control=automation) | Q(variant=automation))
        .exists()
    )


def duplicate(automation, target_workspace, actor):
    """Copy an automation's full graph into another (or the same) workspace. The copy
    is a disabled draft with its own rows, so editing either never touches the other,
    and it never fires until someone in the target workspace publishes it."""
    from .templates import export_automation, import_automation

    return import_automation(
        target_workspace, export_automation(automation), actor, name=f"{automation.name} (copy)"
    )


def transfer(automation, target_workspace, *, operator, reason):
    """Move an automation, its triggers, nodes and edges to another workspace in one
    transaction. In-flight conversation state is dropped: those conversations belong
    to the old workspace and cannot continue a graph the new tenant now owns. The
    moved automation lands disabled, so it never starts firing on an account whose
    owner has not reviewed it."""
    from django.db import transaction

    from .models import AutomationTransferLog, ConversationState, Edge, Node, Trigger

    reason = (reason or "").strip()[:300]
    if not reason:
        raise ValueError("A transfer needs a reason.")
    if str(automation.workspace_id) == str(target_workspace.pk):
        raise ValueError("The automation already belongs to that workspace.")
    if in_experiment(automation):
        raise ValueError("End the A/B experiment using this automation before moving it.")
    with transaction.atomic():
        source = automation.workspace_id
        for model in (Trigger, Node, Edge):
            model.all_objects.filter(automation=automation).update(workspace=target_workspace)
        ConversationState.all_objects.filter(automation=automation).delete()
        automation.workspace = target_workspace
        automation.enabled = False
        automation.save(update_fields=["workspace", "enabled", "updated_at"])
        AutomationTransferLog.objects.create(
            automation_id=automation.pk,
            automation_name=automation.name,
            from_workspace_id=source,
            to_workspace=target_workspace,
            operator=operator,
            reason=reason,
        )
    return automation
