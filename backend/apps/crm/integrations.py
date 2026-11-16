import base64
import json
from abc import ABC, abstractmethod
from datetime import timedelta
from email.message import EmailMessage
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.channels.transport import ProviderError, request


class IntegrationAdapter(ABC):
    @abstractmethod
    def execute(self, operation, payload, idempotency_key): ...


class FakeIntegration(IntegrationAdapter):
    def execute(self, operation, payload, idempotency_key):
        if operation == "check_calendar_availability":
            return {"available": True, "start": payload["start"], "end": payload["end"]}
        return {"id": f"test-{idempotency_key}", "test": True, "operation": operation}


def credentials_for(config):
    from apps.platform_ops.security import assert_enabled

    assert_enabled(config.workspace_id, "integration:" + config.provider)
    credentials = json.loads(config.credentials)
    expiry = parse_datetime(credentials.get("expires_at", ""))
    if (
        config.provider in {"google_calendar", "google_sheets", "gmail"}
        and expiry
        and expiry <= timezone.now() + timedelta(minutes=5)
    ):
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise ProviderError("integration_oauth_not_configured")
        if not credentials.get("refresh_token"):
            raise ProviderError("integration_reconnect_required")
        refreshed = request(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": credentials.get("refresh_token"),
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
            },
        )
        credentials.update(
            access_token=refreshed["access_token"],
            expires_at=(timezone.now() + timedelta(seconds=refreshed["expires_in"])).isoformat(),
        )
        config.credentials = json.dumps(credentials)
        config.save()
    return credentials


class GoogleCalendar(IntegrationAdapter):
    def __init__(self, config):
        self.config = config

    def execute(self, operation, payload, idempotency_key):
        token = credentials_for(self.config).get("access_token")
        if not token:
            raise ProviderError("calendar_credentials_missing")
        headers = {"Authorization": f"Bearer {token}"}
        calendar = self.config.options.get("calendar_id", "primary")
        if operation == "check_calendar_availability":
            body = request(
                "POST",
                "https://www.googleapis.com/calendar/v3/freeBusy",
                headers=headers,
                json={
                    "timeMin": payload["start"],
                    "timeMax": payload["end"],
                    "items": [{"id": calendar}],
                },
            )
            result = body.get("calendars", {}).get(calendar, {})
            return {
                "available": "busy" in result and not result.get("errors") and not result["busy"],
                "start": payload["start"],
                "end": payload["end"],
            }
        if operation != "book_call":
            raise ProviderError("unsupported_integration_operation")
        event_id = idempotency_key.replace("-", "").lower()
        url = f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar, safe='')}/events"
        try:
            body = request(
                "POST",
                url,
                headers=headers,
                side_effect=True,
                json={
                    "id": event_id,
                    "summary": "Sales call",
                    "start": {"dateTime": payload["start"]},
                    "end": {"dateTime": payload["end"]},
                    "attendees": [{"email": payload["email"], "displayName": payload["name"]}],
                },
            )
        except ProviderError as exc:
            if exc.code != "provider_rejected":
                raise
            body = request("GET", f"{url}/{event_id}", headers=headers)
        return {"id": body["id"], "url": body.get("htmlLink", ""), "start": payload["start"]}


class CalCom(IntegrationAdapter):
    def __init__(self, config):
        self.config = config

    def execute(self, operation, payload, idempotency_key):
        credentials = credentials_for(self.config)
        headers = {
            "Authorization": f"Bearer {credentials.get('api_key', '')}",
            "cal-api-version": "2024-09-04",
        }
        event_type = int(self.config.options["event_type_id"])
        if operation == "check_calendar_availability":
            body = request(
                "GET",
                "https://api.cal.com/v2/slots",
                headers={**headers, "cal-api-version": "2024-09-04"},
                params={
                    "start": payload["start"],
                    "end": payload["end"],
                    "eventTypeId": event_type,
                },
            )
            data = body.get("data", {})
            slots = (
                [slot for group in data.values() for slot in group]
                if isinstance(data, dict)
                else []
            )
            return {
                "available": any(
                    parse_datetime(slot.get("start", "")) == parse_datetime(payload["start"])
                    for slot in slots
                ),
                "slots": slots[:20],
            }
        if operation != "book_call":
            raise ProviderError("unsupported_integration_operation")
        body = request(
            "POST",
            "https://api.cal.com/v2/bookings",
            side_effect=True,
            headers=headers,
            json={
                "eventTypeId": event_type,
                "start": payload["start"],
                "attendee": {
                    "name": payload["name"],
                    "email": payload["email"],
                    "timeZone": self.config.options.get("timezone", "UTC"),
                },
                "metadata": {"instantlify_operation": idempotency_key},
            },
        )
        return {"id": body["data"]["uid"], "start": payload["start"]}


class CRMIntegration(IntegrationAdapter):
    def __init__(self, config):
        self.config = config

    def execute(self, operation, payload, idempotency_key):
        credentials = credentials_for(self.config)
        options = self.config.options
        token = credentials.get("api_key") or credentials.get("access_token", "")
        headers = {"Authorization": f"Bearer {token}"}
        provider = self.config.provider
        if provider == "zorromail" and operation == "send_email":
            from django.core.validators import validate_email

            sender = str(options.get("sender_email") or "")
            recipient = str(payload.get("to") or payload.get("email") or "")
            validate_email(sender)
            validate_email(recipient)
            if not token or not str(payload.get("text") or "").strip():
                raise ProviderError("zorromail_configuration_missing")
            email = {
                "from": sender,
                "to": [recipient],
                "subject": str(payload.get("subject") or "Message from our team")[:200],
                "text": str(payload["text"])[:20000],
            }
            if str(options.get("sender_name") or "").strip():
                email["fromName"] = str(options["sender_name"]).strip()[:78]
            body = request(
                "POST",
                "https://www.zorromail.app/tx/v1/messages",
                side_effect=True,
                headers={**headers, "Idempotency-Key": idempotency_key},
                json=email,
            )
            if not body.get("id"):
                raise ProviderError("zorromail_result_unknown")
            suppressed = bool(body.get("suppressedRecipients"))
            return {
                "id": str(body["id"]),
                "status": body.get("status", "accepted"),
                "accepted": not suppressed,
                "suppressed": suppressed,
            }
        if provider == "outlook" and operation == "send_email":
            from django.core.validators import validate_email

            recipient = str(payload.get("to") or payload.get("email") or "")
            validate_email(recipient)
            result = request(
                "POST",
                "https://graph.microsoft.com/v1.0/me/sendMail",
                headers=headers,
                side_effect=True,
                empty_success=True,
                json={
                    "message": {
                        "subject": str(payload.get("subject") or "Message from our team")[:200],
                        "body": {
                            "contentType": "Text",
                            "content": str(payload.get("text") or "")[:20000],
                        },
                        "toRecipients": [{"emailAddress": {"address": recipient}}],
                    },
                    "saveToSentItems": True,
                },
            )
            return {"accepted": bool(result.get("accepted")), "operation": "send_email"}
        if provider in {"n8n", "make", "discord", "webhook"} and operation == "webhook":
            from apps.public_api.outbound import post_public_json

            return post_public_json(
                credentials.get("webhook_url", ""),
                payload["request"],
                authorization=credentials.get("authorization", ""),
                delivery_id=idempotency_key,
            )
        if provider == "gmail" and operation == "send_email":
            from django.core.validators import validate_email

            recipient = str(payload.get("to") or payload.get("email") or "")
            validate_email(recipient)
            sender = str(options.get("sender_email") or "")
            validate_email(sender)
            message = EmailMessage()
            message["From"] = sender
            message["To"] = recipient
            message["Subject"] = str(payload.get("subject") or "Message from our team")[:200]
            message.set_content(str(payload.get("text") or "")[:20000])
            body = request(
                "POST",
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                side_effect=True,
                headers=headers,
                json={"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()},
            )
            if not body.get("id"):
                raise ProviderError("gmail_delivery_unknown")
            return {"id": str(body["id"])}
        if provider == "slack" and operation == "notify":
            body = request(
                "POST",
                "https://slack.com/api/chat.postMessage",
                side_effect=True,
                headers=headers,
                json={
                    "channel": options["channel_id"],
                    "text": str(payload.get("text", "Hot lead received"))[:3000],
                    "client_msg_id": idempotency_key,
                },
            )
            if not body.get("ok"):
                raise ProviderError("slack_rejected")
            return {"id": body["ts"]}
        if operation != "sync_lead":
            raise ProviderError("unsupported_integration_operation")
        if provider == "systeme_io":
            from django.core.validators import validate_email

            email = str(payload.get("email") or "")
            validate_email(email)
            if not token:
                raise ProviderError("integration_credentials_missing")
            systeme_headers = {"X-API-Key": token}
            existing = request(
                "GET",
                "https://api.systeme.io/api/contacts",
                headers=systeme_headers,
                params={"email": email, "limit": 10},
            )
            for contact in existing.get("items", []):
                if str(contact.get("email", "")).casefold() == email.casefold() and contact.get(
                    "id"
                ):
                    return {"id": str(contact["id"]), "existing": True}
            result = request(
                "POST",
                "https://api.systeme.io/api/contacts",
                headers=systeme_headers,
                side_effect=True,
                json={"email": email},
            )
            if not result.get("id"):
                raise ProviderError("systeme_result_unknown")
            return {"id": str(result["id"]), "existing": False}
        if provider in {"mailchimp", "beehiiv", "kit"}:
            return sync_email_list(provider, token, options, payload)
        if provider in {"mailerlite", "klaviyo"}:
            from django.core.validators import validate_email

            email = str(payload.get("email") or "")
            validate_email(email)
            if not token:
                raise ProviderError("integration_credentials_missing")
            name = str(payload.get("name") or "")[:150]
            if provider == "mailerlite":
                group = str(options.get("group_id") or "")
                if not group.isdigit():
                    raise ProviderError("mailerlite_group_missing")
                result = request(
                    "POST",
                    "https://connect.mailerlite.com/api/subscribers",
                    headers=headers,
                    side_effect=True,
                    json={
                        "email": email,
                        "fields": {"name": name},
                        "groups": [group],
                        "resubscribe": False,
                    },
                )
                identifier = result.get("data", {}).get("id")
                if not identifier:
                    raise ProviderError("mailerlite_result_unknown")
                return {"id": str(identifier), "status": result["data"].get("status", "")}
            klaviyo_headers = {
                "Authorization": f"Klaviyo-API-Key {token}",
                "revision": "2026-10-15",
            }
            result = request(
                "POST",
                "https://a.klaviyo.com/api/profile-import",
                headers=klaviyo_headers,
                side_effect=True,
                json={
                    "data": {
                        "type": "profile",
                        "attributes": {
                            "email": email,
                            "first_name": name.split(" ")[0],
                            "last_name": " ".join(name.split(" ")[1:]),
                        },
                    }
                },
            )
            identifier = result.get("data", {}).get("id")
            if not identifier:
                raise ProviderError("klaviyo_result_unknown")
            list_id = str(options.get("list_id") or "")
            if not list_id:
                raise ProviderError("klaviyo_list_missing")
            request(
                "POST",
                f"https://a.klaviyo.com/api/lists/{quote(list_id, safe='')}/relationships/profiles",
                headers=klaviyo_headers,
                side_effect=True,
                empty_success=True,
                json={"data": [{"type": "profile", "id": str(identifier)}]},
            )
            # List membership does not grant or override marketing consent.
            return {"id": str(identifier), "list_id": list_id, "marketing_consent_changed": False}
        if provider == "google_sheets":
            return request(
                "POST",
                f"https://sheets.googleapis.com/v4/spreadsheets/{quote(options['spreadsheet_id'], safe='')}/values/{quote(options.get('range') or 'Sheet1!A:C', safe='')}:append",
                side_effect=True,
                headers=headers,
                params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                json={
                    "values": [
                        [
                            str(payload.get("name") or ""),
                            str(payload.get("email") or ""),
                            str(payload.get("stage") or "new"),
                        ]
                    ]
                },
            )
        if provider == "airtable":
            return request(
                "POST",
                f"https://api.airtable.com/v0/{quote(options['base_id'], safe='')}/{quote(options['table_id'], safe='')}",
                side_effect=True,
                headers=headers,
                json={
                    "records": [
                        {
                            "fields": {
                                "Name": payload.get("name", ""),
                                "Email": payload.get("email", ""),
                                "Stage": payload.get("stage", "new"),
                            }
                        }
                    ]
                },
            )
        if provider == "notion":
            return request(
                "POST",
                "https://api.notion.com/v1/pages",
                side_effect=True,
                headers={**headers, "Notion-Version": "2022-06-28"},
                json={
                    "parent": {"database_id": options["database_id"]},
                    "properties": {
                        "Name": {"title": [{"text": {"content": payload.get("name", "Lead")}}]},
                        "Email": {"email": payload.get("email") or None},
                    },
                },
            )
        if provider == "attio":
            name = payload.get("name") or "Lead"
            return request(
                "PUT",
                "https://api.attio.com/v2/objects/people/records",
                side_effect=True,
                headers=headers,
                params={"matching_attribute": "email_addresses"},
                json={
                    "data": {
                        "values": {
                            "email_addresses": [payload.get("email", "")],
                            "name": [
                                {
                                    "first_name": name.split(" ")[0],
                                    "last_name": " ".join(name.split(" ")[1:]),
                                    "full_name": name,
                                }
                            ],
                        }
                    }
                },
            )
        if provider == "gohighlevel":
            return request(
                "POST",
                "https://services.leadconnectorhq.com/contacts/upsert",
                side_effect=True,
                headers={**headers, "Version": "2021-07-28"},
                json={
                    "locationId": options["location_id"],
                    "email": payload.get("email"),
                    "name": payload.get("name"),
                },
            )
        raise ProviderError("unsupported_integration")


def mailchimp_base(api_key):
    """Mailchimp keys end in their datacenter (abc123-us21)."""
    import re

    dc = api_key.rsplit("-", 1)[-1] if "-" in api_key else ""
    if not re.fullmatch(r"[a-z]{2,4}\d{1,3}", dc):
        raise ProviderError("mailchimp_key_invalid")
    return f"https://{dc}.api.mailchimp.com/3.0"


def sync_email_list(provider, token, options, payload):
    """Add a contact to a Mailchimp audience, Beehiiv publication or Kit account.
    Never grants marketing consent on the lead's behalf: Mailchimp uses double opt-in
    unless the workspace turned it off, Beehiiv sends no welcome email and does not
    reactivate unsubscribed readers, and Kit subscribers are added as-is."""
    import hashlib

    from django.core.validators import validate_email

    email = str(payload.get("email") or "").strip().lower()
    validate_email(email)
    if not token:
        raise ProviderError("integration_credentials_missing")
    name = str(payload.get("name") or "")[:150]
    if provider == "mailchimp":
        list_id = str(options.get("list_id") or "")
        if not list_id:
            raise ProviderError("mailchimp_list_missing")
        double_opt_in = str(options.get("double_opt_in", "true")).lower() != "false"
        member = hashlib.md5(email.encode(), usedforsecurity=False).hexdigest()
        result = request(
            "PUT",
            f"{mailchimp_base(token)}/lists/{quote(list_id, safe='')}/members/{member}",
            auth=("instantlify", token),
            side_effect=True,
            json={
                "email_address": email,
                "status_if_new": "pending" if double_opt_in else "subscribed",
                "merge_fields": {"FNAME": name.split(" ")[0]} if name else {},
            },
        )
        if not result.get("id"):
            raise ProviderError("mailchimp_result_unknown")
        return {"id": str(result["id"]), "status": result.get("status", "")}
    if provider == "beehiiv":
        publication = str(options.get("publication_id") or "")
        if not publication:
            raise ProviderError("beehiiv_publication_missing")
        result = request(
            "POST",
            f"https://api.beehiiv.com/v2/publications/{quote(publication, safe='')}/subscriptions",
            headers={"Authorization": f"Bearer {token}"},
            side_effect=True,
            json={
                "email": email,
                "reactivate_existing": False,
                "send_welcome_email": False,
                "utm_source": "instantlify",
            },
        )
        identifier = (result.get("data") or {}).get("id")
        if not identifier:
            raise ProviderError("beehiiv_result_unknown")
        return {"id": str(identifier)}
    headers = {"X-Kit-Api-Key": token}
    result = request(
        "POST",
        "https://api.kit.com/v4/subscribers",
        headers=headers,
        side_effect=True,
        json={"email_address": email, "first_name": name.split(" ")[0] if name else None},
    )
    subscriber = (result.get("subscriber") or {}).get("id")
    if not subscriber:
        raise ProviderError("kit_result_unknown")
    tag = str(options.get("tag_id") or "")
    if tag:
        request(
            "POST",
            f"https://api.kit.com/v4/tags/{quote(tag, safe='')}/subscribers",
            headers=headers,
            side_effect=True,
            json={"email_address": email},
        )
    return {"id": str(subscriber), "tag_id": tag}


def integration_for(config):
    from apps.platform_ops.security import assert_enabled

    assert_enabled(config.workspace_id, "integration:" + config.provider)
    if not config.enabled:
        raise ProviderError("integration_disabled")
    if config.is_test:
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise ProviderError("test_integration_disabled")
        return FakeIntegration()
    if config.provider == "google_calendar":
        return GoogleCalendar(config)
    if config.provider == "calcom":
        return CalCom(config)
    return CRMIntegration(config)
