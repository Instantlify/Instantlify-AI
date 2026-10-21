import re
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.tenants.services import audit

from .models import Automation, ConversationState, Edge, Node, Trigger

KINDS = {"send_message", "send_buttons", "delay", "condition", "branch", "wait", "end"}


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
        kind = data.get("kind")
        if kind not in KINDS:
            raise ValidationError("Unsupported node type.")
        if kind.startswith("send") and not 1 <= len(data.get("text", "")) <= 2000:
            raise ValidationError("Message nodes require 1–2000 characters.")
        if kind == "send_buttons":
            buttons = data.get("buttons", [])
            if not 1 <= len(buttons) <= 3:
                raise ValidationError("Use 1–3 buttons.")
            for button in buttons:
                if (
                    button.get("type") != "web_url"
                    or not str(button.get("url", "")).startswith("https://")
                    or not 1 <= len(button.get("title", "")) <= 20
                ):
                    raise ValidationError(
                        "Buttons require an HTTPS URL and a title up to 20 characters."
                    )
        if kind == "delay" and not 1 <= int(data.get("seconds", 0)) <= 86400:
            raise ValidationError("Delays must be 1–86400 seconds.")
    for edge in graph["edges"]:
        if edge.get("source") not in nodes or edge.get("target") not in nodes:
            raise ValidationError("Every edge must connect existing nodes.")
    for node_id, node in nodes.items():
        outgoing = [e for e in graph["edges"] if e["source"] == node_id]
        kind = node["data"]["kind"]
        if kind in {"condition", "branch"}:
            if sorted(e.get("sourceHandle", "") for e in outgoing) != ["false", "true"]:
                raise ValidationError("Conditions need exactly one true and one false edge.")
        elif len(outgoing) != (0 if kind == "end" else 1):
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
    if not triggers or len(triggers) > 20:
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
        channel = trigger.get("channel") or ""
        if not isinstance(channel, str) or (
            channel and channel not in TRIGGER_CHANNELS[trigger["kind"]]
        ):
            raise ValidationError("That trigger is not available on the chosen channel.")
    return graph


# Channels each trigger kind can arrive on; a blank channel on a trigger means "any".
TRIGGER_CHANNELS = {
    "dm": {"instagram", "messenger", "whatsapp", "telegram", "linkedin"},
    "comment": {"instagram", "messenger", "linkedin"},
    "story_reply": {"instagram"},
    "live_comment": {"instagram"},
}


@transaction.atomic
def publish(automation, graph, actor):
    graph = validate_graph(graph)
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
        )
    automation.published = graph
    automation.draft = graph
    automation.revision += 1
    automation.enabled = True
    automation.save()
    audit(automation.workspace, actor, "automation.published", automation.id)
    return automation


def keyword_matches(keyword, text):
    return (
        re.search(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", text, flags=re.IGNORECASE)
        is not None
    )


def start_flow(conversation, automation, *, message, comment_id=None, experiment=None, variant=""):
    """Run `automation`'s published graph on this conversation from its start node.
    `message` is the inbound message the flow answers (its text seeds `last_text`)."""
    graph = automation.published
    return ConversationState.objects.for_workspace(conversation.workspace_id).update_or_create(
        conversation=conversation,
        defaults={
            "workspace_id": conversation.workspace_id,
            "automation": automation,
            "graph": graph,
            "node_id": graph["start"],
            "status": "running",
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
        state.variables[node["data"].get("variable", "reply")] = message.text
        state.variables["last_text"] = message.text
        state.node_id = next(
            e["target"] for e in state.graph["edges"] if e["source"] == state.node_id
        )
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
        .filter(automation__enabled=True, kind=payload.get("kind", "dm"))
        .filter(Q(channel="") | Q(channel=provider))
        .select_related("automation")
        .order_by("created_at", "id")
    ):
        if keyword_matches(trigger.keyword, message.text):
            from apps.analytics.services import choose_automation, record

            lead_id = message.conversation.identity.lead_id
            automation, experiment, arm = choose_automation(trigger.automation, lead_id)
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
            return
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
