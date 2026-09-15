import json
from abc import ABC, abstractmethod
from datetime import timedelta
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
    credentials = json.loads(config.credentials)
    expiry = parse_datetime(credentials.get("expires_at", ""))
    if (
        config.provider == "google_calendar"
        and expiry
        and expiry <= timezone.now() + timedelta(minutes=5)
    ):
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
                "metadata": {"nemio_operation": idempotency_key},
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


def integration_for(config):
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
