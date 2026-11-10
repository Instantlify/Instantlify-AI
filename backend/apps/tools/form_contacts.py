from rest_framework import serializers

CONTACT_TYPES = {
    "contact_first_name": "text",
    "contact_last_name": "text",
    "contact_full_name": "text",
    "contact_email": "email",
    "contact_phone": "tel",
    "contact_business": "text",
    "contact_instagram": "text",
    "contact_linkedin": "text",
    "contact_x": "text",
}
EMAIL_TYPES = {"email", "contact_email", "contact_block"}


def clean_contact(field, raw):
    from .form_schema import clean_answer

    if raw in (None, ""):
        raw = {}
    allowed = ("first_name", "last_name", "email", "phone")
    if not isinstance(raw, dict) or set(raw) - set(allowed):
        raise serializers.ValidationError(
            {field["id"]: "Enter the contact details shown in the form."}
        )
    result = {}
    for key in allowed:
        value = raw.get(key, "") if key != "phone" or field.get("include_phone") else ""
        result[key] = clean_answer(
            {
                "id": field["id"],
                "type": "email" if key == "email" else "text",
                "required": field.get("required", False) and key != "phone",
            },
            value,
        )
        if len(result[key]) > (254 if key == "email" else 150):
            raise serializers.ValidationError({field["id"]: "Contact details are too long."})
    return result


def contact_values(fields, answers):
    result = {"email": "", "name": "", "fields": {}}
    mapping = {
        "contact_first_name": "first_name",
        "contact_last_name": "last_name",
        "contact_business": "company",
        "contact_phone": "phone",
        "contact_instagram": "instagram",
        "contact_linkedin": "linkedin",
        "contact_x": "x",
    }
    for field in fields:
        value = answers.get(field["id"])
        if not value:
            continue
        kind = field["type"]
        if kind == "contact_block" and isinstance(value, dict):
            if value.get("email"):
                result["email"] = value["email"]
            result["fields"].update(
                {key: val for key, val in value.items() if key != "email" and val}
            )
        elif isinstance(value, str):
            if kind == "contact_email" or (kind == "email" and not result["email"]):
                result["email"] = value
            elif kind == "contact_full_name" or field["id"] == "name":
                result["name"] = value
            elif kind in mapping:
                result["fields"][mapping[kind]] = value
    if not result["name"]:
        result["name"] = " ".join(
            result["fields"].get(key, "") for key in ("first_name", "last_name")
        ).strip()
    result["name"] = result["name"][:150]
    result["email"] = result["email"].lower()
    return result
