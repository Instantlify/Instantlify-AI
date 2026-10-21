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

triggers: 1-3 items {"kind", "keyword", "channel"}.
  kind: "comment" (post/reel comment), "dm", "story_reply" or "live_comment".
  channel: "instagram", "messenger", "whatsapp" or "" for any. WhatsApp only supports
  "dm"; Messenger supports "dm" and "comment"; story_reply and live_comment are
  Instagram only. keyword: one short word the customer types, e.g. "SEND".
nodes: {"id": short slug, "data": {...}} where data.kind is one of
  "send_message" {"text"} - text up to 2000 characters;
  "send_buttons" {"text", "buttons": [{"type": "web_url", "url": "https://...",
    "title": up to 20 characters}]} - 1-3 buttons;
  "wait" {"variable"} - pauses until the customer replies, saved as {{variable}};
  "condition" {"variable", "equals"} - case-insensitive equality check;
  "delay" {"seconds"} - 1-86400;
  "end" {} - finishes the flow.
edges: {"source", "target"}; a condition has exactly two edges with "sourceHandle"
  "true" and "false". Every node except end has exactly one outgoing edge, every node
  is reachable from start, and there are no cycles. Use {{name}} placeholders only for
  variables saved by an earlier wait node. When a link is needed but not given, use
  https://example.com and say so in the message text.
"""

NODE_FIELDS = {"kind", "text", "buttons", "seconds", "variable", "equals"}


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
