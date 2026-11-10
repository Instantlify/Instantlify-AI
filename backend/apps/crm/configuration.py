"""Local setup checks only. Saving does not contact the provider; use the integration
"Test connection" action (crm/connection_test.py) to verify credentials."""

from rest_framework import serializers


def validate_live_configuration(provider, credentials, options):
    webhook_providers = {"n8n", "make", "discord", "webhook"}
    token_fields = (
        ("webhook_url",)
        if provider in webhook_providers
        else ("secret_key",)
        if provider == "stripe"
        else ("access_token",)
        if provider in {"gmail", "google_calendar", "google_sheets", "outlook"}
        else ("api_key", "access_token")
    )
    if not any(
        isinstance(credentials.get(key), str) and credentials[key].strip() for key in token_fields
    ):
        raise serializers.ValidationError(
            {
                "credentials": "Enter the provider's "
                + " or ".join(key.replace("_", " ") for key in token_fields)
                + "."
            }
        )
    required_options = {
        "google_sheets": ("spreadsheet_id",),
        "gmail": ("sender_email",),
        "zorromail": ("sender_email",),
        "slack": ("channel_id",),
        "airtable": ("base_id", "table_id"),
        "gohighlevel": ("location_id",),
        "calcom": ("event_type_id",),
        "mailchimp": ("list_id",),
        "beehiiv": ("publication_id",),
    }.get(provider, ())
    missing = [
        key.replace("_", " ") for key in required_options if not str(options.get(key) or "").strip()
    ]
    if missing:
        raise serializers.ValidationError({"options": "Enter " + ", ".join(missing) + "."})
