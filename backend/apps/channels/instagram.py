from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .adapters import Credentials, InstagramAdapter, IntegrationUnavailable
from .transport import ProviderError, request


class LiveInstagramAdapter(InstagramAdapter):
    def __init__(self, connection):
        self.connection = connection

    def send_message(
        self, *, recipient_id, text, idempotency_key, buttons=None, private_reply=False
    ):
        recipient = {"comment_id" if private_reply else "id": recipient_id}
        message = {"text": text}
        if buttons:
            message = {
                "attachment": {
                    "type": "template",
                    "payload": {"template_type": "button", "text": text, "buttons": buttons},
                }
            }
        body = request(
            "POST",
            self.url("messages"),
            side_effect=True,
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
            json={"recipient": recipient, "message": message},
        )
        if not body.get("message_id"):
            from .transport import AmbiguousDelivery

            raise AmbiguousDelivery()
        return body["message_id"]

    def url(self, resource):
        return f"https://graph.instagram.com/{settings.META_API_VERSION}/{self.connection.external_account_id}/{resource}"

    def send_voice_note(self, *, recipient_id, media_url, idempotency_key):
        body = request(
            "POST",
            self.url("messages"),
            side_effect=True,
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
            json={
                "recipient": {"id": recipient_id},
                "message": {"attachment": {"type": "audio", "payload": {"url": media_url}}},
            },
        )
        return body.get("message_id", "")

    def headers(self):
        return {"Authorization": f"Bearer {self.connection.access_token}"}

    def hide_comment(self, comment_id):
        request(
            "POST",
            f"https://graph.instagram.com/{settings.META_API_VERSION}/{comment_id}",
            side_effect=True,
            headers=self.headers(),
            json={"hide": True},
        )

    def delete_comment(self, comment_id):
        request(
            "DELETE",
            f"https://graph.instagram.com/{settings.META_API_VERSION}/{comment_id}",
            side_effect=True,
            headers=self.headers(),
        )

    def create_media_container(self, *, caption, media_url, media_type):
        payload = {"caption": caption[:2200]}
        if media_type == "video":
            payload.update(media_type="REELS", video_url=media_url)
        else:
            payload.update(image_url=media_url)
        container = request("POST", self.url("media"), headers=self.headers(), data=payload)
        if not container.get("id"):
            raise ProviderError("media_container_failed")
        return str(container["id"])

    def container_status(self, container_id):
        body = request(
            "GET",
            f"https://graph.instagram.com/{settings.META_API_VERSION}/{container_id}",
            headers=self.headers(),
            params={"fields": "status_code,status"},
        )
        return str(body.get("status_code") or "IN_PROGRESS").upper()

    def publish_container(self, container_id):
        published = request(
            "POST",
            self.url("media_publish"),
            side_effect=True,
            headers=self.headers(),
            data={"creation_id": container_id},
        )
        return published.get("id", "")

    def refresh_token(self, credentials):
        body = request(
            "GET",
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": credentials.access_token},
        )
        return Credentials(
            credentials.account_id,
            credentials.display_name,
            body["access_token"],
            timezone.now() + timedelta(seconds=int(body["expires_in"])),
        )


def live_exchange(code):
    if not settings.META_APP_ID or not settings.META_APP_SECRET or not code:
        raise IntegrationUnavailable("Meta credentials are not configured")
    short = request(
        "POST",
        "https://api.instagram.com/oauth/access_token",
        data={
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": settings.META_REDIRECT_URI,
            "code": code,
        },
    )
    long = request(
        "GET",
        "https://graph.instagram.com/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": settings.META_APP_SECRET,
            "access_token": short["access_token"],
        },
    )
    profile = request(
        "GET",
        f"https://graph.instagram.com/{settings.META_API_VERSION}/me",
        params={"fields": "user_id,username,name,biography,website,followers_count"},
        headers={"Authorization": f"Bearer {long['access_token']}"},
    )
    account_id = str(profile.get("user_id") or profile.get("id") or "")
    if not account_id:
        raise ProviderError("missing_account_id")
    request(
        "POST",
        f"https://graph.instagram.com/{settings.META_API_VERSION}/{account_id}/subscribed_apps",
        headers={"Authorization": f"Bearer {long['access_token']}"},
        data={"subscribed_fields": "messages,messaging_postbacks,comments"},
    )
    return Credentials(
        account_id,
        profile.get("username", account_id),
        long["access_token"],
        timezone.now() + timedelta(seconds=int(long["expires_in"])),
        profile={
            "name": profile.get("name", ""),
            "biography": profile.get("biography", ""),
            "website": profile.get("website", ""),
            "followers_count": profile.get("followers_count", 0),
        },
    )
