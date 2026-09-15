from urllib.parse import quote

from django.conf import settings

from .adapters import InstagramAdapter
from .transport import AmbiguousDelivery, ProviderError, request


class WhatsAppAdapter(InstagramAdapter):
    def __init__(self, connection):
        self.connection = connection

    def _send(self, recipient_id, content):
        body = request(
            "POST",
            f"https://graph.facebook.com/{settings.META_API_VERSION}/{self.connection.external_account_id}/messages",
            side_effect=True,
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
            json={"messaging_product": "whatsapp", "to": recipient_id, **content},
        )
        try:
            return body["messages"][0]["id"]
        except (KeyError, IndexError):
            raise AmbiguousDelivery() from None

    def send_message(self, *, recipient_id, text, idempotency_key):
        return self._send(recipient_id, {"type": "text", "text": {"body": text}})

    def send_voice_note(self, *, recipient_id, media_url, idempotency_key):
        return self._send(recipient_id, {"type": "audio", "audio": {"link": media_url}})


class MessengerAdapter(InstagramAdapter):
    """Facebook Page messaging: same Send API shape as Instagram, Page-scoped IDs."""

    def __init__(self, connection):
        self.connection = connection

    def _send(self, recipient_id, message):
        body = request(
            "POST",
            f"https://graph.facebook.com/{settings.META_API_VERSION}/{self.connection.external_account_id}/messages",
            side_effect=True,
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
            json={
                "recipient": {"id": recipient_id},
                "messaging_type": "RESPONSE",
                "message": message,
            },
        )
        if not body.get("message_id"):
            raise AmbiguousDelivery()
        return body["message_id"]

    def send_message(self, *, recipient_id, text, idempotency_key, buttons=None):
        message = {"text": text}
        if buttons:
            message = {
                "attachment": {
                    "type": "template",
                    "payload": {"template_type": "button", "text": text, "buttons": buttons},
                }
            }
        return self._send(recipient_id, message)

    def send_voice_note(self, *, recipient_id, media_url, idempotency_key):
        return self._send(
            recipient_id,
            {"attachment": {"type": "audio", "payload": {"url": media_url, "is_reusable": False}}},
        )


class TelegramAdapter(InstagramAdapter):
    def __init__(self, connection):
        self.connection = connection

    def call(self, method, data):
        body = request(
            "POST",
            f"https://api.telegram.org/bot{quote(self.connection.access_token, safe=':')}/{method}",
            side_effect=True,
            json=data,
        )
        if not body.get("ok"):
            raise ProviderError("telegram_rejected")
        return body["result"]

    def send_message(self, *, recipient_id, text, idempotency_key):
        return str(self.call("sendMessage", {"chat_id": recipient_id, "text": text})["message_id"])

    def send_voice_note(self, *, recipient_id, media_url, idempotency_key):
        return str(
            self.call("sendVoice", {"chat_id": recipient_id, "voice": media_url})["message_id"]
        )

    def configure_webhook(self, url):
        return self.call(
            "setWebhook",
            {
                "url": url,
                "secret_token": self.connection.webhook_secret,
                "allowed_updates": ["message", "callback_query"],
            },
        )
