from urllib.parse import quote

from django.conf import settings

from .adapters import InstagramAdapter
from .transport import AmbiguousDelivery, ProviderError, request


class WhatsAppAdapter(InstagramAdapter):
    def send_media(self, *, recipient_id, media_url, media_type, idempotency_key):
        return self._send(recipient_id, {"type": media_type, media_type: {"link": media_url}})

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

    def send_message(self, *, recipient_id, text, idempotency_key, buttons=None):
        replies = [button for button in (buttons or []) if button["type"] == "postback"]
        links = [button for button in (buttons or []) if button["type"] == "web_url"]
        if links:
            text += "\n\n" + "\n".join(f"{b['title']}: {b['url']}" for b in links)
        if replies:
            if len(text) > 1024:
                raise ProviderError("interactive_message_too_long")
            return self._send(
                recipient_id,
                {
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {"text": text},
                        "action": {
                            "buttons": [
                                {
                                    "type": "reply",
                                    "reply": {"id": b["payload"], "title": b["title"]},
                                }
                                for b in replies
                            ]
                        },
                    },
                },
            )
        # Resource URLs remain usable on WhatsApp without requiring an approved template.
        if len(text) > 4096:
            raise ProviderError("message_too_long")
        return self._send(recipient_id, {"type": "text", "text": {"body": text}})

    def send_voice_note(self, *, recipient_id, media_url, idempotency_key):
        return self._send(recipient_id, {"type": "audio", "audio": {"link": media_url}})


class MessengerAdapter(InstagramAdapter):
    def send_media(self, *, recipient_id, media_url, media_type, idempotency_key):
        return self._send(
            recipient_id,
            {
                "attachment": {
                    "type": media_type,
                    "payload": {"url": media_url, "is_reusable": False},
                }
            },
        )

    """Facebook Page messaging: same Send API shape as Instagram, Page-scoped IDs."""

    def __init__(self, connection):
        self.connection = connection

    def _send(self, recipient_id, message, private_reply=False):
        body = request(
            "POST",
            f"https://graph.facebook.com/{settings.META_API_VERSION}/{self.connection.external_account_id}/messages",
            side_effect=True,
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
            json={
                # A private reply answers a Page comment in Messenger, addressed by comment ID.
                "recipient": {"comment_id" if private_reply else "id": recipient_id},
                "messaging_type": "RESPONSE",
                "message": message,
            },
        )
        if not body.get("message_id"):
            raise AmbiguousDelivery()
        return body["message_id"]

    def send_message(
        self, *, recipient_id, text, idempotency_key, buttons=None, private_reply=False
    ):
        message = {"text": text}
        if buttons:
            message = {
                "attachment": {
                    "type": "template",
                    "payload": {"template_type": "button", "text": text, "buttons": buttons},
                }
            }
        return self._send(recipient_id, message, private_reply)

    def send_voice_note(self, *, recipient_id, media_url, idempotency_key):
        return self._send(
            recipient_id,
            {"attachment": {"type": "audio", "payload": {"url": media_url, "is_reusable": False}}},
        )

    def recent_posts(self):
        body = request(
            "GET",
            f"https://graph.facebook.com/{settings.META_API_VERSION}/{self.connection.external_account_id}/posts",
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
            params={"fields": "id,message,permalink_url", "limit": 50},
        )
        return [
            {
                "id": str(p["id"]),
                "label": str(p.get("message") or p["id"])[:200],
                "permalink": str(p.get("permalink_url") or ""),
            }
            for p in body.get("data", [])
        ]

    def owns_post(self, post_id):
        body = request(
            "GET",
            f"https://graph.facebook.com/{settings.META_API_VERSION}/{post_id}",
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
            params={"fields": "from"},
        )
        return str((body.get("from") or {}).get("id", "")) == self.connection.external_account_id

    def next_post(self, since):
        from .commenting import first_post_after

        return first_post_after(
            lambda after: request(
                "GET",
                f"https://graph.facebook.com/{settings.META_API_VERSION}/{self.connection.external_account_id}/posts",
                headers={"Authorization": f"Bearer {self.connection.access_token}"},
                params={
                    "fields": "id,created_time",
                    "limit": 50,
                    **({"after": after} if after else {}),
                },
            ),
            since,
            "created_time",
        )

    def reply_comment(self, *, comment_id, text, idempotency_key):
        body = request(
            "POST",
            f"https://graph.facebook.com/{settings.META_API_VERSION}/{comment_id}/comments",
            side_effect=True,
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
            data={"message": text},
        )
        if not body.get("id"):
            raise AmbiguousDelivery()
        return str(body["id"])

    def fetch_profile(self, sender_id):
        body = request(
            "GET",
            f"https://graph.facebook.com/{settings.META_API_VERSION}/{sender_id}",
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
            params={"fields": "first_name,last_name,profile_pic"},
        )
        name = " ".join(
            part for part in (body.get("first_name", ""), body.get("last_name", "")) if part
        )
        return {"name": name, "handle": "", "avatar_url": str(body.get("profile_pic") or "")}

    def hide_comment(self, comment_id):
        request(
            "POST",
            f"https://graph.facebook.com/{settings.META_API_VERSION}/{comment_id}",
            side_effect=True,
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
            json={"is_hidden": True},
        )

    def delete_comment(self, comment_id):
        request(
            "DELETE",
            f"https://graph.facebook.com/{settings.META_API_VERSION}/{comment_id}",
            side_effect=True,
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
        )


class TelegramAdapter(InstagramAdapter):
    def send_media(self, *, recipient_id, media_url, media_type, idempotency_key):
        method, field = {
            "image": ("sendPhoto", "photo"),
            "video": ("sendVideo", "video"),
            "audio": ("sendAudio", "audio"),
        }[media_type]
        body = self.call(method, {"chat_id": recipient_id, field: media_url})
        if not body.get("message_id"):
            raise AmbiguousDelivery()
        return str(body["message_id"])

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

    def send_message(self, *, recipient_id, text, idempotency_key, buttons=None):
        body = {"chat_id": recipient_id, "text": text}
        if buttons:
            body["reply_markup"] = {
                "inline_keyboard": [
                    [
                        {
                            "text": button["title"],
                            ("url" if button["type"] == "web_url" else "callback_data"): button.get(
                                "url"
                            )
                            if button["type"] == "web_url"
                            else button["payload"],
                        }
                    ]
                    for button in buttons
                ]
            }
        return str(self.call("sendMessage", body)["message_id"])

    def send_voice_note(self, *, recipient_id, media_url, idempotency_key):
        return str(
            self.call("sendVoice", {"chat_id": recipient_id, "voice": media_url})["message_id"]
        )

    def fetch_profile(self, sender_id):
        chat = self.call("getChat", {"chat_id": sender_id})
        name = " ".join(
            part for part in (chat.get("first_name", ""), chat.get("last_name", "")) if part
        ) or str(chat.get("title") or "")
        username = str(chat.get("username") or "")
        return {"name": name, "handle": "@" + username if username else "", "avatar_url": ""}

    def configure_webhook(self, url):
        return self.call(
            "setWebhook",
            {
                "url": url,
                "secret_token": self.connection.webhook_secret,
                "allowed_updates": ["message", "callback_query"],
            },
        )


class LinkedInAdapter:
    """Unproven against a real account. LinkedIn does not hand out messaging access to
    ordinary apps, so `adapters.adapter_for` refuses this provider unless
    LINKEDIN_MESSAGING_APPROVED says the grant was confirmed. Verify the endpoint and
    payload below against the app's own documentation before turning that on.
    """

    def __init__(self, connection):
        self.connection = connection

    def send_message(self, *, recipient_id, text, idempotency_key):
        if settings.CHANNEL_ADAPTER_MODE == "fake":
            return f"fake-li-msg-{idempotency_key}"
        # Live LinkedIn Organization messages / comment replies
        body = request(
            "POST",
            "https://api.linkedin.com/v2/messages",
            headers={
                "Authorization": f"Bearer {self.connection.access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json={
                "recipients": [recipient_id],
                "body": text,
            },
        )
        return str(body.get("id") or f"li-{idempotency_key}")

    def send_voice_note(self, *, recipient_id, media_url, idempotency_key):
        raise ProviderError("unsupported_media_type")
