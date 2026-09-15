"""Safety contracts written before the integration and execution foundations."""

import hashlib
import hmac

import pytest

from apps.automations.engine import InvalidTransition, advance
from apps.channels.signatures import verify_meta_signature


def signature(body, secret="test-app-secret"):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_signature_accepts_exact_bytes_only():
    body = b'{"message":"hello"}'
    assert verify_meta_signature(body, signature(body), "test-app-secret")
    assert not verify_meta_signature(body + b" ", signature(body), "test-app-secret")


@pytest.mark.parametrize("header", [None, "", "sha1=123", "sha256=", "sha256=" + "z" * 64])
def test_missing_or_malformed_signature_is_rejected(header):
    assert not verify_meta_signature(b"{}", header, "test-app-secret")


def test_wrong_secret_and_empty_secret_are_rejected():
    assert not verify_meta_signature(b"{}", signature(b"{}"), "wrong")
    assert not verify_meta_signature(b"{}", signature(b"{}", ""), "")


def test_waiting_state_resumes_only_with_input():
    graph = {"start": {"kind": "wait", "next": "done"}, "done": {"kind": "end"}}
    assert advance(graph, "start", has_input=False, steps=0).node_id == "start"
    result = advance(graph, "start", has_input=True, steps=0)
    assert result.node_id == "done"
    assert advance(graph, "done", has_input=False, steps=1).finished


def test_one_step_returns_intent_without_executing_side_effects():
    graph = {"a": {"kind": "send_message", "next": "b"}, "b": {"kind": "end"}}
    result = advance(graph, "a", has_input=False, steps=0)
    assert result.action == "send_message"
    assert result.node_id == "b"
    assert result.steps == 1


def test_runaway_cycles_stop_at_budget():
    with pytest.raises(InvalidTransition):
        advance({"a": {"kind": "send_message", "next": "a"}}, "a", steps=32)


@pytest.mark.parametrize(
    "graph,node",
    [
        ({}, "missing"),
        ({"a": {"kind": "code"}}, "a"),
        ({"a": {"kind": "send_message", "next": "missing"}}, "a"),
    ],
)
def test_invalid_graph_cannot_emit_action(graph, node):
    with pytest.raises(InvalidTransition):
        advance(graph, node, steps=0)
