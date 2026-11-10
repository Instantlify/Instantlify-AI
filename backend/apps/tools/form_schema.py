"""Shared definition and answer validation for public forms.

Branch destinations must move forward. The server derives the visible path and
never trusts the browser to decide which required questions may be skipped.
"""

import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator, validate_email
from rest_framework import serializers

from .form_contacts import CONTACT_TYPES, EMAIL_TYPES

FIELD_TYPES = {
    "text",
    "textarea",
    "email",
    "tel",
    "select",
    "number",
    "date",
    "url",
    "checkboxes",
    "yes_no",
    "rating",
    "opinion_scale",
    "file_upload",
    "signature",
    "cover_card",
    "calendly",
    "calcom",
    "tidycal",
    "contact_block",
    *CONTACT_TYPES,
}
BOOKING_HOSTS = {
    "calendly": {"calendly.com", "www.calendly.com"},
    "calcom": {"cal.com", "www.cal.com"},
    "tidycal": {"tidycal.com", "www.tidycal.com"},
}
NON_INPUT_TYPES = {"cover_card", *BOOKING_HOSTS}


def validate_fields(value, require_email=True):
    if not isinstance(value, list) or not 1 <= len(value) <= 100:
        raise serializers.ValidationError("Add 1–100 questions, including a required email field.")
    seen = set()
    for field in value:
        if not isinstance(field, dict) or set(field) - {
            "id",
            "label",
            "type",
            "required",
            "options",
            "min",
            "max",
            "description",
            "booking_url",
            "include_phone",
        }:
            raise serializers.ValidationError("Invalid question configuration.")
        key = field.get("id")
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key)
            or key in seen
        ):
            raise serializers.ValidationError(
                "Use unique lowercase answer names up to 40 characters."
            )
        seen.add(key)
        if not isinstance(field.get("label"), str) or not 1 <= len(field["label"].strip()) <= 120:
            raise serializers.ValidationError("Each question needs a label up to 120 characters.")
        if (
            not isinstance(field.get("type"), str)
            or field["type"] not in FIELD_TYPES
            or not isinstance(field.get("required", False), bool)
        ):
            raise serializers.ValidationError("Unsupported question type or required setting.")
        description = field.get("description", "")
        if not isinstance(field.get("include_phone", False), bool):
            raise serializers.ValidationError("Choose whether to include a phone number.")
        if not isinstance(description, str) or len(description) > 1000:
            raise serializers.ValidationError(
                "Question descriptions support up to 1000 characters."
            )
        if field["type"] in NON_INPUT_TYPES and field.get("required"):
            raise serializers.ValidationError(
                "Welcome cards and embedded calendars cannot be required answers."
            )
        if field["type"] in BOOKING_HOSTS:
            url = field.get("booking_url", "")
            if not isinstance(url, str) or len(url) > 2000:
                raise serializers.ValidationError("Enter a public booking URL.")
            try:
                parsed = urlsplit(url)
                valid = (
                    parsed.scheme == "https"
                    and parsed.hostname in BOOKING_HOSTS[field["type"]]
                    and not parsed.username
                    and not parsed.password
                    and parsed.port in {None, 443}
                    and parsed.path not in {"", "/"}
                )
            except ValueError:
                valid = False
            if not valid:
                raise serializers.ValidationError(
                    "Use a public HTTPS booking page on the selected provider's domain."
                )
        if field["type"] in {"select", "checkboxes"}:
            options = field.get("options")
            if (
                not isinstance(options, list)
                or not 1 <= len(options) <= 30
                or any(not isinstance(v, str) or not 1 <= len(v.strip()) <= 120 for v in options)
                or len(set(options)) != len(options)
            ):
                raise serializers.ValidationError("Use 1–30 distinct, nonempty choices.")
            normalized = [option.strip() for option in options]
            if len(set(normalized)) != len(normalized):
                raise serializers.ValidationError(
                    "Choices must remain distinct after trimming spaces."
                )
            field["options"] = normalized
        low, high = field.get("min"), field.get("max")
        for bound in (low, high):
            if bound is not None and (
                type(bound) not in {int, float} or not math.isfinite(bound) or abs(bound) > 1e12
            ):
                raise serializers.ValidationError("Question limits must be finite numbers.")
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError("The minimum cannot exceed the maximum.")
        if field["type"] in {"rating", "opinion_scale"}:
            low, high = bounds(field)
            if not isinstance(low, int) or not isinstance(high, int) or not 0 <= low < high <= 10:
                raise serializers.ValidationError(
                    "Rating scales need whole-number limits between 0 and 10."
                )
    if require_email and not any(f["type"] in EMAIL_TYPES and f.get("required") for f in value):
        raise serializers.ValidationError(
            "Include a required email question with answer name email."
        )
    return value


def bounds(field):
    if field["type"] == "rating":
        return field.get("min", 1), field.get("max", 5)
    if field["type"] == "opinion_scale":
        return field.get("min", 0), field.get("max", 10)
    return field.get("min"), field.get("max")


def validate_branching(rules, fields):
    if not isinstance(rules, list) or len(rules) > 100:
        raise serializers.ValidationError("Use up to 100 branching rules.")
    positions = {f["id"]: i for i, f in enumerate(fields)}
    seen = set()
    email_index = next(
        (
            i
            for i, field in enumerate(fields)
            if field["type"] in EMAIL_TYPES and field.get("required")
        ),
        -1,
    )
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"field_id", "answer", "next_id"}:
            raise serializers.ValidationError("Each rule needs a question, answer and destination.")
        source, answer, target = rule["field_id"], rule["answer"], rule["next_id"]
        if isinstance(answer, str):
            answer = answer.strip()
            rule["answer"] = answer
        if (
            not isinstance(source, str)
            or source not in positions
            or not isinstance(answer, str)
            or not 1 <= len(answer) <= 2000
        ):
            raise serializers.ValidationError("Choose an existing question and a nonempty answer.")
        source_index = positions[source]
        if fields[source_index]["type"] in {
            "checkboxes",
            "file_upload",
            "signature",
            "contact_block",
            *NON_INPUT_TYPES,
        }:
            raise serializers.ValidationError("Branch from a single-answer question.")
        if target is not None and (
            not isinstance(target, str)
            or target not in positions
            or positions[target] <= source_index
        ):
            raise serializers.ValidationError(
                "Branch destinations must be later questions or the end of the form."
            )
        destination = positions[target] if target is not None else len(fields)
        if source_index < email_index < destination:
            raise serializers.ValidationError("A branch cannot skip the required email question.")
        if (source, answer) in seen:
            raise serializers.ValidationError("Use only one destination per question and answer.")
        seen.add((source, answer))
    return rules


def clean_answer(field, raw):
    key, kind = field["id"], CONTACT_TYPES.get(field["type"], field["type"])

    def reject(message):
        raise serializers.ValidationError({key: message})

    if kind == "contact_block":
        from .form_contacts import clean_contact

        return clean_contact(field, raw)

    if kind in {"file_upload", "signature"}:
        from .form_files import clean_file

        return clean_file(field, raw)

    if kind == "checkboxes":
        if raw in (None, ""):
            raw = []
        if (
            not isinstance(raw, list)
            or len(raw) > 30
            or any(not isinstance(v, str) or v not in field["options"] for v in raw)
            or len(set(raw)) != len(raw)
        ):
            reject("Choose from the listed options without duplicates.")
        if field.get("required") and not raw:
            reject("Choose at least one option.")
        return raw
    if not isinstance(raw, str) or len(raw) > 2000:
        reject("Use up to 2000 text characters.")
    value = raw.strip()
    if not value:
        if field.get("required"):
            reject("This field is required.")
        return ""
    if kind == "email":
        try:
            validate_email(value)
        except DjangoValidationError:
            reject("Enter a valid email address.")
        if len(value) > 254:
            reject("Email address is too long.")
    elif kind == "url":
        try:
            URLValidator(schemes=["https", "http"])(value)
        except DjangoValidationError:
            reject("Enter a complete HTTP or HTTPS web address.")
    elif kind == "date":
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError
            date.fromisoformat(value)
        except ValueError:
            reject("Enter a valid date.")
    elif kind in {"number", "rating", "opinion_scale"}:
        try:
            number = Decimal(value)
            if not number.is_finite() or abs(number) > Decimal("1e12"):
                raise InvalidOperation
            low, high = bounds(field)
            if (low is not None and number < Decimal(str(low))) or (
                high is not None and number > Decimal(str(high))
            ):
                reject("Choose a number within the allowed range.")
            if kind != "number" and number != number.to_integral_value():
                reject("Choose a whole-number rating.")
        except InvalidOperation:
            reject("Enter a finite number.")
    elif kind == "select" and value not in field["options"]:
        reject("Choose one of the listed options.")
    elif kind == "yes_no" and value not in {"yes", "no"}:
        reject("Choose Yes or No.")
    return value


def clean_answers(fields, rules, values):
    if not isinstance(values, dict) or set(values) - {f["id"] for f in fields}:
        raise serializers.ValidationError("Submit only the questions in this form.")
    positions = {f["id"]: i for i, f in enumerate(fields)}
    answers, index = {}, 0
    while index < len(fields):
        field = fields[index]
        if field["type"] in NON_INPUT_TYPES:
            index += 1
            continue
        value = clean_answer(field, values.get(field["id"], ""))
        answers[field["id"]] = value
        rule = next(
            (r for r in rules if r["field_id"] == field["id"] and r["answer"] == value), None
        )
        if rule:
            index = positions[rule["next_id"]] if rule["next_id"] is not None else len(fields)
        else:
            index += 1
    from .form_files import MAX_TOTAL_BYTES

    if (
        sum(value.get("size", 0) for value in answers.values() if isinstance(value, dict))
        > MAX_TOTAL_BYTES
    ):
        raise serializers.ValidationError("Use no more than 2 MB of attachments per response.")
    # Skipped answers are deliberately discarded, including forged hidden values.
    return answers
