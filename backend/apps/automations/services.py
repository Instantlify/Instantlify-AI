import re
from datetime import timedelta

from django.db import transaction
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
            trigger.get("kind") not in {"dm", "comment", "story_reply", "live_comment"}
            or not 1 <= len(trigger.get("keyword", "")) <= 100
        ):
            raise ValidationError("Invalid trigger.")
    return graph


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
            workspace_id=automation.workspace_id, automation=automation, **trigger
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
    for trigger in (
        []
        if cooling
        else Trigger.objects.for_workspace(message.workspace_id)
        .filter(automation__enabled=True, kind=payload.get("kind", "dm"))
        .select_related("automation")
        .order_by("created_at", "id")
    ):
        if keyword_matches(trigger.keyword, message.text):
            from apps.analytics.services import choose_automation, record

            lead_id = message.conversation.identity.lead_id
            automation, experiment, arm = choose_automation(trigger.automation, lead_id)
            graph = automation.published
            ConversationState.objects.for_workspace(message.workspace_id).update_or_create(
                conversation=message.conversation,
                defaults={
                    "workspace_id": message.workspace_id,
                    "automation": automation,
                    "graph": graph,
                    "node_id": graph["start"],
                    "status": "running",
                    "steps": 0,
                    "variables": {
                        "last_text": message.text,
                        "comment_id": payload.get("comment_id"),
                    },
                    "available_at": timezone.now(),
                    "last_message_id": message.id,
                    "cooldown_until": timezone.now() + timedelta(hours=1),
                    "experiment_id": experiment.pk if experiment else None,
                    "variant": arm,
                },
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
