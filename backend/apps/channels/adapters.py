"""Provider-neutral boundary. Live Instagram transport is a Phase 1 gate."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone


class IntegrationUnavailable(Exception):
    pass


@dataclass(frozen=True)
class IncomingMessage:
    event_id: str
    account_id: str
    sender_id: str
    text: str


@dataclass(frozen=True)
class Credentials:
    account_id: str
    display_name: str
    access_token: str = field(repr=False)
    expires_at: datetime


class ChannelAdapter(ABC):
    @abstractmethod
    def send_message(self, *, recipient_id: str, text: str, idempotency_key: str) -> str: ...

    @abstractmethod
    def send_voice_note(
        self, *, recipient_id: str, media_url: str, idempotency_key: str
    ) -> str: ...

    @abstractmethod
    def parse_incoming_webhook(self, payload: dict) -> list[IncomingMessage]: ...

    @abstractmethod
    def refresh_token(self, credentials: Credentials) -> Credentials: ...

    def publish_post(self, *, caption: str, media_url: str, media_type: str) -> str:
        """Publish to the account's own feed (content calendar). Optional per channel."""
        raise NotImplementedError("unsupported_provider")


class InstagramAdapter(ChannelAdapter):
    def send_message(self, **kwargs):
        raise IntegrationUnavailable("Live Instagram sending ships after Phase 1 verification")

    def send_voice_note(self, **kwargs):
        raise IntegrationUnavailable("Live voice sending is not available")

    def parse_incoming_webhook(self, payload):
        messages = []
        for entry in payload.get("entry", []):
            for event in entry.get("messaging", []):
                message = event.get("message", {})
                if message.get("mid") and not message.get("is_echo"):
                    messages.append(
                        IncomingMessage(
                            event_id=message["mid"],
                            account_id=str(entry["id"]),
                            sender_id=str(event["sender"]["id"]),
                            text=message.get("text", ""),
                        )
                    )
        return messages

    def refresh_token(self, credentials):
        raise IntegrationUnavailable("Live token refresh ships in Phase 1")


class FakeChannelAdapter(InstagramAdapter):
    """In-memory test double; explicitly selected, never a live fallback."""

    def __init__(self):
        self.sent = {}

    def send_message(self, *, recipient_id, text, idempotency_key):
        self.sent.setdefault(idempotency_key, (recipient_id, text))
        return idempotency_key

    def send_voice_note(self, *, recipient_id, media_url, idempotency_key):
        return self.send_message(
            recipient_id=recipient_id, text=media_url, idempotency_key=idempotency_key
        )

    def publish_post(self, *, caption, media_url, media_type):
        return "fake-post-" + str(abs(hash((caption, media_url))))[:12]

    def refresh_token(self, credentials):
        return Credentials(
            credentials.account_id,
            credentials.display_name,
            "fake-token",
            timezone.now() + timedelta(days=60),
        )


def exchange_oauth_code(code, workspace_id):
    if settings.CHANNEL_ADAPTER_MODE == "live":
        from apps.platform_ops.metrics import workspace_metrics
        from apps.platform_ops.security import assert_enabled

        from .instagram import live_exchange

        assert_enabled(workspace_id, "integration:instagram")
        with workspace_metrics(workspace_id):
            return live_exchange(code)
    if settings.CHANNEL_ADAPTER_MODE != "fake":
        raise IntegrationUnavailable("Live Meta OAuth exchange is gated on Phase 1")
    if code != "local-test-code":
        raise IntegrationUnavailable("Invalid local OAuth code")
    return Credentials(
        f"fake-{workspace_id}",
        "Local test account",
        "fake-token-not-a-real-secret",
        timezone.now() + timedelta(days=60),
    )


def adapter_for(connection):
    from apps.platform_ops.security import assert_enabled

    assert_enabled(connection.workspace_id, "integration:" + connection.provider)
    if connection.is_test:
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise IntegrationUnavailable("Test connections are disabled")
        return FakeChannelAdapter()
    if settings.CHANNEL_ADAPTER_MODE != "live":
        raise IntegrationUnavailable("Live connections are disabled")
    from .instagram import LiveInstagramAdapter
    from .providers import MessengerAdapter, TelegramAdapter, WhatsAppAdapter

    return {
        "instagram": LiveInstagramAdapter,
        "whatsapp": WhatsAppAdapter,
        "telegram": TelegramAdapter,
        "messenger": MessengerAdapter,
    }[connection.provider](connection)


PROVIDERS = ["instagram", "whatsapp", "telegram", "messenger"]
# Channels with a platform-enforced customer-service window for free-form replies.
WINDOWED_PROVIDERS = {"instagram", "whatsapp", "messenger"}
