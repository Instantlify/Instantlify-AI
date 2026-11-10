"""Turn a model's answer into a flow graph. The model only proposes; every draft passes
the same validation as a hand-built flow, and anything outside the schema is dropped."""

import json

from rest_framework.exceptions import ValidationError

from .services import validate_graph

# FakeLLMProvider recognises this marker; keep the first line stable.
SYSTEM_PROMPT = """You are the Nemio flow designer.
Design one messaging automation for Instagram, Facebook Messenger or WhatsApp from the
user's request. Answer with a single JSON object and nothing else:
{"name": str, "start": node id, "triggers": [...], "nodes": [...], "edges": [...]}

triggers: 1-3 items {"kind", "keyword", "channel", optional "match"}.
  match: "keyword" (default; keyword must appear in the message) or "intent" (keyword is a
  short description of what the message means, e.g. "asks about price"; use it when the
  user describes a meaning rather than an exact word).
  kind: "comment" (post/reel comment), "dm", "story_reply" or "live_comment".
  channel: "instagram", "messenger", "whatsapp" or "" for any. WhatsApp only supports
  "dm"; Messenger supports "dm" and "comment"; story_reply and live_comment are
  Instagram only. keyword: one short word the customer types, e.g. "SEND".
nodes: {"id": short slug, "data": {...}} where data.kind is one of
  "send_message" {"text"} - text up to 2000 characters;
  "follow_gate" {"text", "button_title", "expected_reply"} - Instagram only; prompts for a private response, then verifies the follow with Instagram before continuing;
  "send_reminder" {"text", "source_node"} - after a delay, follow up only if the earlier source send_buttons message with track_clicks:true has not been clicked;
  "ai_generate" {"prompt", "variable"} - generates text into a saved variable, does not send it automatically;
  "ai_extract" {"prompt", "fields": ["field_name"], "variable"} - extracts named scalar fields into flow variables;
  "ai_agent" {"prompt" (goal and instructions), optional "persona", "max_turns" 1-20, "use_knowledge"} - chats with the customer toward the goal, then continues; use it for open-ended qualifying or support conversations;
  "ai_condition" {"prompt", "variable"} - evaluates instructions and branches using true/false edges;
  "send_media" {"media_type": "image"|"video"|"audio", "media_url": "https://..."} - a direct public file URL provided by the user; requires a private reply first for comment triggers;
  "send_buttons" {"text", "buttons": [{"type": "web_url", "url": "https://...",
    "title": up to 20 characters}]} - 1-3 buttons;
  "wait" {"variable"} - pauses until the customer replies, saved as {{variable}};
  "condition" {"match": "all"|"any", "rules": [{"subject": "variable"|"field"|"tag"|"stage"|"email"|"channel", "name" (variable or field name), "operator": "equals"|"not_equals"|"contains"|"not_contains"|"starts_with"|"ends_with"|"is_set"|"is_not_set"|"greater_than"|"less_than", "value"}]} - case-insensitive; tags use contains/not_contains/is_set/is_not_set;
  "delay" {"seconds", optional "seconds_max" for a random window} - 1 second to 30 days (2592000);
  "set_field" {"field", "value"} - a contact field name up to 60 characters and value up to 500;
  "set_stage" {"stage"} - new, qualified, interested, booked, won or lost;
  "randomizer" {"percentage"} - weighted split, first path 0-100 percent, with true and false edges;
  "end" {} - finishes the flow.
edges: {"source", "target"}; a condition, ai_condition or randomizer has exactly two edges with "sourceHandle"
  "true" and "false". Every node except end has exactly one outgoing edge, every node
  is reachable from start, and there are no cycles. Use {{name}} placeholders only for
  variables saved by an earlier wait node. When a link is needed but not given, use
  https://example.com and say so in the message text.
"""

NODE_FIELDS = {
    "button_title",
    "expected_reply",
    "track_clicks",
    "source_node",
    "prompt",
    "fields",
    "ai_provider",
    "ai_model",
    "media_type",
    "media_url",
    "kind",
    "text",
    "buttons",
    "seconds",
    "variable",
    "equals",
    "rules",
    "match",
    "persona",
    "max_turns",
    "use_knowledge",
    "knowledge_base_id",
    "seconds_max",
    "timeout_seconds",
    "field",
    "value",
    "stage",
    "percentage",
}


def _json_object(text):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValidationError("The AI answer did not contain a flow. Try rephrasing.")
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        raise ValidationError("The AI answer was not a readable flow. Try rephrasing.") from None
    if not isinstance(data, dict):
        raise ValidationError("The AI answer was not a readable flow. Try rephrasing.")
    return data


def _layout(graph):
    """Top-to-bottom positions by distance from the start node."""
    children = {}
    for edge in graph["edges"]:
        children.setdefault(edge["source"], []).append(edge["target"])
    depth, queue = {graph["start"]: 0}, [graph["start"]]
    while queue:
        node_id = queue.pop(0)
        for child in children.get(node_id, []):
            if child not in depth:
                depth[child] = depth[node_id] + 1
                queue.append(child)
    columns = {}
    for node in graph["nodes"]:
        row = depth.get(node["id"], len(depth))
        column = columns.get(row, 0)
        columns[row] = column + 1
        node["position"] = {"x": 80 + column * 280, "y": 80 + row * 170}


def graph_from_completion(text):
    data = _json_object(text or "")
    nodes = data.get("nodes") if isinstance(data.get("nodes"), list) else []
    edges = data.get("edges") if isinstance(data.get("edges"), list) else []
    triggers = data.get("triggers") if isinstance(data.get("triggers"), list) else []
    graph = {
        "start": data.get("start"),
        "triggers": [
            {
                "kind": item.get("kind"),
                "keyword": item.get("keyword"),
                "channel": item.get("channel") or "",
                **({"match": "intent"} if item.get("match") == "intent" else {}),
            }
            for item in triggers
            if isinstance(item, dict)
        ],
        "nodes": [
            {
                "id": node.get("id"),
                "data": {
                    key: value
                    for key, value in (node.get("data") or {}).items()
                    if key in NODE_FIELDS
                },
            }
            for node in nodes
            if isinstance(node, dict) and isinstance(node.get("data"), dict)
        ],
        "edges": [
            {
                "id": f"{edge.get('source')}-{edge.get('target')}-{index}",
                "source": edge.get("source"),
                "target": edge.get("target"),
                **(
                    {"sourceHandle": edge["sourceHandle"]}
                    if edge.get("sourceHandle") in {"true", "false"}
                    else {}
                ),
            }
            for index, edge in enumerate(edges)
            if isinstance(edge, dict)
        ],
    }
    try:
        validate_graph(graph)
    except ValidationError as exc:
        detail = exc.detail if isinstance(exc.detail, list) else [exc.detail]
        raise ValidationError(
            "The AI draft was not a valid flow ("
            + " ".join(str(item) for item in detail)
            + ") Try rephrasing the request."
        ) from None
    except (AttributeError, KeyError, TypeError, ValueError):
        # Wrongly typed fields (a number for text, a string for seconds) fail here.
        raise ValidationError(
            "The AI draft was not a valid flow. Try rephrasing the request."
        ) from None
    _layout(graph)
    name = str(data.get("name") or "").strip()[:100] or "AI-drafted flow"
    return name, graph
