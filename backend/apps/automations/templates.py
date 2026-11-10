"""Portable automation definitions: export, validate and import graphs as JSON."""

import json

from rest_framework.exceptions import ValidationError

from .models import Automation
from .services import validate_graph

FORMAT = "nemio.automation"
VERSION = 1
MAX_BYTES = 200_000


def export_automation(automation):
    graph = automation.published or automation.draft
    return {
        "format": FORMAT,
        "version": VERSION,
        "name": automation.name,
        "graph": graph,
    }


def parse_template(document):
    """Accept an export document (dict or JSON string) and return (name, validated graph)."""
    if isinstance(document, str | bytes):
        if len(document) > MAX_BYTES:
            raise ValidationError("Template is too large.")
        try:
            document = json.loads(document)
        except ValueError:
            raise ValidationError("Template is not valid JSON.") from None
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise ValidationError("This file is not an Instantlify automation template.")
    version = document.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValidationError("Template version must be a positive integer.")
    if version > VERSION:
        raise ValidationError("This template needs a newer version of Instantlify.")
    if len(json.dumps(document)) > MAX_BYTES:
        raise ValidationError("Template is too large.")
    name = str(document.get("name", "Imported automation")).strip()[:100] or "Imported automation"
    graph = validate_graph(document.get("graph"))
    # Only the graph's own keys are imported; anything else in the file is ignored.
    return name, {
        key: graph[key]
        for key in [
            "start",
            "nodes",
            "edges",
            "triggers",
            "connection_id",
            "comment_post_ids",
            "comment_replies",
            "comment_post_mode",
        ]
        if key in graph
    }


def import_automation(workspace, document, actor, *, installed_from=None, name=None):
    from apps.tenants.services import audit

    parsed_name, graph = parse_template(document)
    automation = Automation.objects.for_workspace(workspace).create(
        workspace=workspace,
        name=name or parsed_name,
        draft=graph,
        enabled=False,
        installed_from=installed_from,
    )
    audit(workspace, actor, "automation.imported", automation.id)
    return automation
