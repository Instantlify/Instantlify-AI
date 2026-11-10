"""Condition rules for `condition`/`branch` steps, shared by the runtime and preview.

A condition holds 1–10 rules combined with "all" (AND) or "any" (OR). Each rule reads
one subject (a flow variable, a contact field, the contact's tags, stage, email or the
channel) and compares it with an operator. Older flows saved only `variable` and
`equals`; they read as a single case-insensitive equality rule, so they keep working.
"""

import re

from rest_framework.exceptions import ValidationError

SUBJECTS = {"variable", "field", "tag", "stage", "email", "channel"}
OPERATORS = {
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "is_set",
    "is_not_set",
    "greater_than",
    "less_than",
}
# Operators that ignore the rule's value.
UNARY = {"is_set", "is_not_set"}
# Tags are a set: only membership questions make sense.
TAG_OPERATORS = {"contains", "not_contains", "is_set", "is_not_set"}
NAME = re.compile(r"[\w.-]{1,40}")


def rules_for(data):
    """The condition's rules, upgrading the legacy single-equality shape."""
    rules = data.get("rules")
    if isinstance(rules, list) and rules:
        return rules
    return [
        {
            "subject": "variable",
            "name": data.get("variable") or "last_text",
            "operator": "equals",
            "value": data.get("equals", ""),
        }
    ]


def validate_condition(data):
    match = data.get("match", "all")
    if match not in {"all", "any"}:
        raise ValidationError("Choose whether all or any rules must match.")
    if "rules" in data and (not isinstance(data["rules"], list) or not data["rules"]):
        raise ValidationError("A condition needs 1–10 rules.")
    rules = rules_for(data)
    if not isinstance(rules, list) or not 1 <= len(rules) <= 10:
        raise ValidationError("A condition needs 1–10 rules.")
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValidationError("Each condition rule must be an object.")
        subject = rule.get("subject", "variable")
        operator = rule.get("operator", "equals")
        if subject not in SUBJECTS:
            raise ValidationError("Choose what the condition checks.")
        if operator not in OPERATORS:
            raise ValidationError("Choose a valid comparison.")
        if subject == "tag" and operator not in TAG_OPERATORS:
            raise ValidationError("Tags can only be checked for whether the contact has them.")
        if subject in {"variable", "field"}:
            name = rule.get("name", "")
            if not isinstance(name, str) or not NAME.fullmatch(name):
                raise ValidationError("Name the variable or field to check (letters, digits, _).")
        value = rule.get("value", "")
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise ValidationError("A condition value must be text or a number.")
        if len(str(value)) > 200:
            raise ValidationError("A condition value can have at most 200 characters.")
        if operator in {"greater_than", "less_than"} and _number(value) is None:
            raise ValidationError("Number comparisons need a numeric value.")
        if subject == "tag" and operator not in UNARY and not str(value).strip():
            raise ValidationError("Enter the tag to check for.")


def _number(value):
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _compare(actual, operator, expected):
    if operator == "is_set":
        return actual not in (None, "", [], {})
    if operator == "is_not_set":
        return actual in (None, "", [], {})
    if operator in {"greater_than", "less_than"}:
        left, right = _number(actual), _number(expected)
        if left is None or right is None:
            return False
        return left > right if operator == "greater_than" else left < right
    text = str("" if actual is None else actual).strip().casefold()
    target = str(expected).strip().casefold()
    return {
        "equals": text == target,
        "not_equals": text != target,
        "contains": target in text,
        "not_contains": target not in text,
        "starts_with": text.startswith(target),
        "ends_with": text.endswith(target),
    }[operator]


def _subject_value(rule, context):
    subject = rule.get("subject", "variable")
    if subject == "variable":
        return context["variables"].get(rule.get("name") or "last_text")
    if subject == "field":
        return context["fields"].get(rule.get("name", ""))
    return context.get(subject)


def evaluate_rule(rule, context):
    operator = rule.get("operator", "equals")
    value = rule.get("value", "")
    if rule.get("subject") == "tag":
        tags = {str(tag).strip().casefold() for tag in context.get("tags") or []}
        if operator in UNARY:
            return bool(tags) if operator == "is_set" else not tags
        has = str(value).strip().casefold() in tags
        return has if operator == "contains" else not has
    return _compare(_subject_value(rule, context), operator, value)


def evaluate(data, context):
    """True/False for a condition step against a context built by `context_for`."""
    results = (evaluate_rule(rule, context) for rule in rules_for(data))
    return any(results) if data.get("match", "all") == "any" else all(results)


def context_for(state):
    """Runtime context: the flow's variables plus the live contact record."""
    identity = state.conversation.identity
    lead = identity.lead
    return {
        "variables": state.variables,
        "fields": lead.fields if isinstance(lead.fields, dict) else {},
        "tags": lead.tags if isinstance(lead.tags, list) else [],
        "stage": lead.stage,
        "email": lead.email,
        "channel": identity.connection.provider,
    }


def describe(data):
    """Short human description, used in previews."""
    labels = {
        "equals": "is",
        "not_equals": "is not",
        "contains": "contains",
        "not_contains": "does not contain",
        "starts_with": "starts with",
        "ends_with": "ends with",
        "is_set": "is set",
        "is_not_set": "is empty",
        "greater_than": ">",
        "less_than": "<",
    }
    parts = []
    for rule in rules_for(data):
        subject = rule.get("subject", "variable")
        name = rule.get("name") if subject in {"variable", "field"} else subject
        operator = rule.get("operator", "equals")
        if subject == "tag":
            text = {
                "contains": f"has tag “{rule.get('value', '')}”",
                "not_contains": f"lacks tag “{rule.get('value', '')}”",
                "is_set": "has any tag",
                "is_not_set": "has no tags",
            }[operator]
        elif operator in UNARY:
            text = f"{name} {labels[operator]}"
        else:
            text = f"{name} {labels[operator]} “{rule.get('value', '')}”"
        parts.append(text)
    return (" and " if data.get("match", "all") == "all" else " or ").join(parts)
