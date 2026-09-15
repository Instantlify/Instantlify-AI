"""Phase 0 pure safety kernel. Persistent graph execution ships in Phase 2."""

from dataclasses import dataclass


class InvalidTransition(ValueError):
    pass


@dataclass(frozen=True)
class Transition:
    node_id: str
    steps: int
    action: str | None = None
    finished: bool = False


def advance(graph: dict, node_id: str, *, steps: int, has_input: bool = False) -> Transition:
    if steps < 0 or steps >= 32 or node_id not in graph:
        raise InvalidTransition("Invalid state or execution budget exceeded")
    node = graph[node_id]
    kind = node.get("kind")
    if kind == "end":
        return Transition(node_id, steps, finished=True)
    if kind not in {"wait", "send_message"}:
        raise InvalidTransition("Unsupported node kind")
    target = node.get("next")
    if target not in graph:
        raise InvalidTransition("Missing target node")
    if kind == "wait" and not has_input:
        return Transition(node_id, steps)
    return Transition(target, steps + 1, action=kind if kind == "send_message" else None)
