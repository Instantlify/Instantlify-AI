"""Side-effect-free graph walkthrough. External results must be supplied as samples."""

import json
import re

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership

from .services import ANY_KEYWORD, keyword_matches, validate_graph


def preview(graph, replies, samples, trigger_event=None):
    graph = validate_graph(graph)
    if (
        not isinstance(replies, list)
        or len(replies) > 100
        or any(not isinstance(v, str) or len(v) > 2000 for v in replies)
    ):
        raise ValidationError("Supply up to 100 sample replies of 2000 characters each.")
    if not isinstance(samples, dict) or len(json.dumps(samples)) > 20000:
        raise ValidationError("Sample results must be a JSON object under 20 KB.")
    variables = {"last_text": replies[0] if replies else ""}
    if trigger_event is not None:
        if not isinstance(trigger_event, dict):
            raise ValidationError("Supply a sample event with a kind, channel and text.")
        kind, channel, text = (trigger_event.get(key) for key in ("kind", "channel", "text"))
        if not all(
            isinstance(value, str) and len(value) <= 2000 for value in (kind, channel, text)
        ):
            raise ValidationError("Supply a sample event with a kind, channel and text.")
        matched = any(
            trigger["kind"] == kind
            and (not trigger.get("channel") or trigger["channel"] == channel)
            and (trigger["keyword"] == ANY_KEYWORD or keyword_matches(trigger["keyword"], text))
            for trigger in graph["triggers"]
        )
        if not matched:
            return {"trace": [], "side_effects": False, "trigger_matched": False}
        variables["last_text"] = text
    remaining = iter(replies)
    nodes = {n["id"]: n["data"] for n in graph["nodes"]}
    node_id = graph["start"]
    trace = []
    for _ in range(100):
        data = nodes[node_id]
        kind = data["kind"]
        entry = {"node_id": node_id, "kind": kind, "detail": "", "status": "simulated"}
        trace.append(entry)
        branch = ""
        if kind in {"end", "transfer", "start_agent"}:
            entry["detail"] = (
                "End of this graph"
                if kind == "end"
                else "Would continue to the configured automation or agent"
            )
            break
        if kind in {"wait", "capture_email"}:
            reply = next(remaining, None)
            if reply is None:
                entry.update(status="waiting", detail="Add a sample reply to continue")
                break
            if data.get("expected_reply") and data["expected_reply"] != reply:
                entry.update(
                    status="waiting",
                    detail="The sample reply does not match the required button response",
                )
                break
            if kind == "capture_email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", reply):
                entry.update(
                    status="waiting", detail="The sample email is invalid; the real flow asks again"
                )
                break
            variables[data.get("variable", "reply")] = reply
            if kind == "capture_email":
                variables["email"] = reply
            variables["last_text"] = reply
        elif kind in {
            "ai_generate",
            "ai_extract",
            "ai_condition",
            "follow_gate",
            "integration_action",
            "randomizer",
            "send_reminder",
        }:
            if node_id not in samples:
                entry.update(
                    status="waiting",
                    detail="Provide a sample result for this node; no provider is called",
                )
                break
            sample = samples[node_id]
            if kind in {
                "ai_condition",
                "randomizer",
                "follow_gate",
                "send_reminder",
            } and not isinstance(sample, bool):
                raise ValidationError(f"Node {node_id} needs a true/false sample.")
            if kind == "follow_gate" and not sample:
                entry.update(
                    status="waiting",
                    detail="Would ask the lead to follow and wait for another private reply",
                )
                break
            if kind in {"ai_condition", "randomizer"}:
                branch = "true" if sample else "false"
            elif kind in {"ai_generate", "ai_extract", "integration_action"}:
                variables[
                    data.get(
                        "variable",
                        "integration_result" if kind == "integration_action" else "ai_result",
                    )
                ] = sample
                if kind == "ai_extract" and isinstance(sample, dict):
                    variables.update(sample)
                if kind == "integration_action" and data.get("operation") == "webhook":
                    mapping = data.get("response_map", {})
                    if isinstance(mapping, str):
                        mapping = json.loads(mapping)
                    for variable, path in mapping.items():
                        value = sample
                        try:
                            for part in path.split("."):
                                value = value[int(part)] if isinstance(value, list) else value[part]
                        except (KeyError, IndexError, TypeError, ValueError):
                            raise ValidationError(
                                "A mapped sample response field is missing."
                            ) from None
                        variables[variable] = value
            if kind == "follow_gate":
                variables["following"] = True
            entry["detail"] = "Using your sample result"
            if kind == "send_reminder":
                entry["detail"] = (
                    "Would skip: the resource was clicked"
                    if sample
                    else "Would send the reminder: " + data["text"]
                )
        elif kind in {"condition", "branch"}:
            branch = (
                "true"
                if str(variables.get(data.get("variable", "last_text"), "")).casefold()
                == str(data.get("equals", "")).casefold()
                else "false"
            )
        elif kind == "delay":
            entry["detail"] = f"Would wait {data['seconds']} seconds"
        elif kind == "avatar_video":
            entry["detail"] = (
                "Would create an avatar video, wait for rendering and send it privately; no provider called"
            )
        elif kind == "ai_call":
            entry["detail"] = (
                "Would check a private call request and phone number, then schedule the call in its permitted window; no call is placed"
            )
        elif kind == "generate_voice":
            entry["detail"] = (
                "Would synthesize and send voice with the configured provider; no provider called"
            )
        elif kind == "send_media":
            entry["detail"] = f"Would send {data['media_type']}: {data['media_url']}"
        elif kind in {"send_message", "send_buttons"}:
            text = data["text"]
            for key, value in variables.items():
                text = text.replace("{{" + key + "}}", str(value)[:2000])
            entry["detail"] = text
        else:
            entry["detail"] = "Would apply the configured CRM action"
        if branch:
            entry["detail"] = f"{entry['detail']} · {branch} branch".strip(" ·")
        node_id = next(
            e["target"]
            for e in graph["edges"]
            if e["source"] == node_id and e.get("sourceHandle", "") == branch
        )
    result = {"trace": trace, "side_effects": False}
    if trigger_event is not None:
        result["trigger_matched"] = True
    return result


class PreviewView(APIView):
    def post(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        return Response(
            preview(
                request.data.get("graph"),
                request.data.get("replies", []),
                request.data.get("samples", {}),
                request.data.get("trigger_event"),
            )
        )
