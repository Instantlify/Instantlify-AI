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
    # Public profile facts, when the provider returns them. Never secret.
    profile: dict = field(default_factory=dict)


class ChannelAdapter(ABC):
    def following_status(self, sender_id):
        raise IntegrationUnavailable("This channel cannot verify followers")

    def send_media(self, *, recipient_id, media_url, media_type, idempotency_key):
        raise IntegrationUnavailable("This channel cannot send media")

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

    # Content calendar (optional per channel). Publishing is three steps because video
    # containers process asynchronously and must not be published until FINISHED.
    def create_media_container(self, *, caption: str, media_url: str, media_type: str) -> str:
        raise NotImplementedError("unsupported_provider")

    def container_status(self, container_id: str) -> str:
        """IN_PROGRESS, FINISHED, ERROR, EXPIRED or PUBLISHED (Meta's status_code)."""
        raise NotImplementedError("unsupported_provider")

    def hide_comment(self, comment_id: str) -> None:
        raise IntegrationUnavailable("This channel cannot hide comments")

    def recent_posts(self) -> list[dict]:
        raise IntegrationUnavailable("This channel cannot list posts")

    def owns_post(self, post_id: str) -> bool:
        raise IntegrationUnavailable("This channel cannot verify posts")

    def next_post(self, since) -> str | None:
        raise IntegrationUnavailable("This channel cannot find the next published post")

    def reply_comment(self, *, comment_id: str, text: str, idempotency_key: str) -> str:
        raise IntegrationUnavailable("This channel cannot reply to comments")

    def delete_comment(self, comment_id: str) -> None:
        raise IntegrationUnavailable("This channel cannot delete comments")

    def publish_container(self, container_id: str) -> str:
        raise NotImplementedError("unsupported_provider")

    def fetch_profile(self, sender_id: str) -> dict:
        """Public facts about a person who messaged: name, handle and avatar_url. Channels
        without a profile lookup return {} and keep whatever the webhook carried."""
        return {}


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
    def following_status(self, sender_id):
        return True  # Explicit test connections simulate a successful follow.

    def send_media(self, *, recipient_id, media_url, media_type, idempotency_key):
        return self.send_message(
            recipient_id=recipient_id, text=media_url, idempotency_key=idempotency_key
        )

    """In-memory test double; explicitly selected, never a live fallback."""

    def __init__(self):
        self.sent = {}
        self.moderated = []

    def send_message(self, *, recipient_id, text, idempotency_key):
        self.sent.setdefault(idempotency_key, (recipient_id, text))
        return idempotency_key

    def send_voice_note(self, *, recipient_id, media_url, idempotency_key):
        return self.send_message(
            recipient_id=recipient_id, text=media_url, idempotency_key=idempotency_key
        )

    def create_media_container(self, *, caption, media_url, media_type):
        return "fake-container-" + str(abs(hash((caption, media_url))))[:12]

    def container_status(self, container_id):
        return "FINISHED"

    def publish_container(self, container_id):
        return container_id.replace("fake-container-", "fake-post-")

    def hide_comment(self, comment_id):
        self.moderated.append(("hide", comment_id))

    def recent_posts(self):
        return [
            {"id": f"test-post-{i}", "label": f"Test post {i}", "permalink": ""} for i in (1, 2)
        ]

    def owns_post(self, post_id):
        return post_id in {p["id"] for p in self.recent_posts()}

    def next_post(self, since):
        return None

    def reply_comment(self, *, comment_id, text, idempotency_key):
        return self.send_message(
            recipient_id=comment_id, text=text, idempotency_key=idempotency_key
        )

    def delete_comment(self, comment_id):
        self.moderated.append(("delete", comment_id))

    def fetch_profile(self, sender_id):
        # Deterministic, so the simulator and tests show a person rather than an ID.
        words = [part for part in sender_id.replace("_", "-").split("-") if part]
        return {
            "name": " ".join(word.capitalize() for word in words) or sender_id,
            "handle": "@" + sender_id.lower().replace("-", "."),
            "avatar_url": "",
        }

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


class WebChatAdapter(ChannelAdapter):
    """Website chat: replies are stored and read back by the visitor's widget, so a
    delivery is complete as soon as it is recorded."""

    def send_message(self, *, recipient_id, text, idempotency_key, **kwargs):
        return "webchat:" + idempotency_key

    def send_voice_note(self, *, recipient_id, media_url, idempotency_key):
        return "webchat:" + idempotency_key

    def parse_incoming_webhook(self, payload):
        return []

    def refresh_token(self, credentials):
        return credentials


def adapter_for(connection):
    from apps.platform_ops.security import assert_enabled

    assert_enabled(connection.workspace_id, "integration:" + connection.provider)
    if connection.provider == "webchat":
        return WebChatAdapter()
    if connection.is_test:
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise IntegrationUnavailable("Test connections are disabled")
        return FakeChannelAdapter()
    if settings.CHANNEL_ADAPTER_MODE != "live":
        raise IntegrationUnavailable("Live connections are disabled")
    if connection.provider == "linkedin" and not settings.LINKEDIN_MESSAGING_APPROVED:
        raise IntegrationUnavailable(
            "LinkedIn messaging access for this app has not been confirmed"
        )
    from .instagram import LiveInstagramAdapter
    from .providers import LinkedInAdapter, MessengerAdapter, TelegramAdapter, WhatsAppAdapter

    return {
        "instagram": LiveInstagramAdapter,
        "whatsapp": WhatsAppAdapter,
        "telegram": TelegramAdapter,
        "messenger": MessengerAdapter,
        "linkedin": LinkedInAdapter,
    }[connection.provider](connection)


PROVIDERS = ["instagram", "whatsapp", "telegram", "messenger", "linkedin"]
# Channels with a platform-enforced customer-service window for free-form replies.
WINDOWED_PROVIDERS = {"instagram", "whatsapp", "messenger"}
