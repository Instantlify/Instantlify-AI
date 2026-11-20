from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.utils import timezone

from .adapters import Credentials, InstagramAdapter, IntegrationUnavailable
from .transport import ProviderError, request


class LiveInstagramAdapter(InstagramAdapter):
    @property
    def graph_url(self):
        host = (
            "graph.facebook.com"
            if (self.connection.profile or {}).get("unified_login")
            else "graph.instagram.com"
        )
        return f"https://{host}/{settings.META_API_VERSION}"

    def following_status(self, sender_id):
        body = request(
            "GET",
            f"{self.graph_url}/{sender_id}",
            headers=self.headers(),
            params={"fields": "is_user_follow_business"},
        )
        value = body.get("is_user_follow_business")
        if not isinstance(value, bool):
            raise ProviderError("follow_status_unavailable")
        return value

    def send_media(self, *, recipient_id, media_url, media_type, idempotency_key):
        body = request(
            "POST",
            self.url("messages"),
            side_effect=True,
            headers=self.headers(),
            json={
                "recipient": {"id": recipient_id},
                "message": {"attachment": {"type": media_type, "payload": {"url": media_url}}},
            },
        )
        if not body.get("message_id"):
            from .transport import AmbiguousDelivery

            raise AmbiguousDelivery()
        return str(body["message_id"])

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
        return f"{self.graph_url}/{self.connection.external_account_id}/{resource}"

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

    def fetch_profile(self, sender_id):
        body = request(
            "GET",
            f"{self.graph_url}/{sender_id}",
            headers=self.headers(),
            params={"fields": "name,username,profile_pic"},
        )
        username = str(body.get("username") or "")
        return {
            "name": str(body.get("name") or username or ""),
            "handle": "@" + username if username else "",
            "avatar_url": str(body.get("profile_pic") or ""),
        }

    def hide_comment(self, comment_id):
        request(
            "POST",
            f"{self.graph_url}/{comment_id}",
            side_effect=True,
            headers=self.headers(),
            json={"hide": True},
        )

    def recent_posts(self):
        body = request(
            "GET",
            self.url("media"),
            headers=self.headers(),
            params={"fields": "id,caption,permalink", "limit": 50},
        )
        return [
            {
                "id": str(p["id"]),
                "label": str(p.get("caption") or p["id"])[:200],
                "permalink": str(p.get("permalink") or ""),
            }
            for p in body.get("data", [])
        ]

    def owns_post(self, post_id):
        body = request(
            "GET",
            f"{self.graph_url}/{post_id}",
            headers=self.headers(),
            params={"fields": "owner"},
        )
        return str((body.get("owner") or {}).get("id", "")) == self.connection.external_account_id

    def next_post(self, since):
        from .commenting import first_post_after

        return first_post_after(
            lambda after: request(
                "GET",
                self.url("media"),
                headers=self.headers(),
                params={
                    "fields": "id,timestamp",
                    "limit": 50,
                    **({"after": after} if after else {}),
                },
            ),
            since,
            "timestamp",
        )

    def reply_comment(self, *, comment_id, text, idempotency_key):
        body = request(
            "POST",
            f"{self.graph_url}/{comment_id}/replies",
            side_effect=True,
            headers=self.headers(),
            data={"message": text},
        )
        if not body.get("id"):
            from .transport import AmbiguousDelivery

            raise AmbiguousDelivery()
        return str(body["id"])

    def delete_comment(self, comment_id):
        request(
            "DELETE",
            f"{self.graph_url}/{comment_id}",
            side_effect=True,
            headers=self.headers(),
        )

    def create_media_container(self, *, caption, media_url, media_type):
        self.check_publishing_access()
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
        self.check_publishing_access()
        body = request(
            "GET",
            f"{self.graph_url}/{container_id}",
            headers=self.headers(),
            params={"fields": "status_code,status"},
        )
        return str(body.get("status_code") or "IN_PROGRESS").upper()

    def publish_container(self, container_id):
        self.check_publishing_access()
        published = request(
            "POST",
            self.url("media_publish"),
            side_effect=True,
            headers=self.headers(),
            data={"creation_id": container_id},
        )
        return published.get("id", "")

    def check_publishing_access(self):
        from apps.platform_ops.capabilities import has_capability

        if not has_capability(self.connection.workspace_id, "meta_publishing"):
            raise ProviderError("capability_approval_required")

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
    if settings.INSTAGRAM_UNIFIED_LOGIN_CONFIG_ID:
        return unified_exchange(code)
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
        meta_authorizer_id=str(short.get("user_id") or account_id),
        profile={
            "name": profile.get("name", ""),
            "biography": profile.get("biography", ""),
            "website": profile.get("website", ""),
            "followers_count": profile.get("followers_count", 0),
        },
    )


def unified_exchange(code):
    graph_url = f"https://graph.facebook.com/{settings.META_API_VERSION}"
    token = request(
        "GET",
        f"{graph_url}/oauth/access_token",
        params={
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "redirect_uri": settings.META_REDIRECT_URI,
            "code": code,
        },
    )["access_token"]
    debug = request(
        "GET",
        f"{graph_url}/debug_token",
        params={"input_token": token},
        headers={"Authorization": f"Bearer {settings.META_APP_ID}|{settings.META_APP_SECRET}"},
    )["data"]
    if not debug.get("is_valid") or str(debug.get("app_id")) != settings.META_APP_ID:
        raise ProviderError("invalid_instagram_token")
    messaging_scope = "instagram_manage_messages"
    messaging_grants = [
        permission
        for permission in debug.get("granular_scopes") or []
        if permission.get("scope") == messaging_scope
    ]
    if not messaging_grants and messaging_scope not in (debug.get("scopes") or []):
        raise ProviderError("instagram_messaging_grant_missing")
    headers = {"Authorization": f"Bearer {token}"}
    accounts = {
        str(account_id)
        for permission in messaging_grants
        for account_id in permission.get("target_ids") or []
        if account_id
    }
    if not accounts:
        # Unified Login issues a business-integration system-user token whose
        # granular scopes may omit target_ids; the granted Instagram accounts are
        # then listed as the system user's assigned assets instead.
        assigned = (
            request(
                "GET",
                f"{graph_url}/me/assigned_instagram_accounts",
                params={"fields": "id,username"},
                headers=headers,
            ).get("data")
            or []
        )
        accounts = {str(item["id"]) for item in assigned if item.get("id")}
    if not accounts:
        raise ProviderError("instagram_messaging_grant_has_no_targets")
    if len(accounts) > 1:
        raise ProviderError("instagram_messaging_grant_has_multiple_targets")
    account_id = accounts.pop()
    profile = request(
        "GET",
        f"{graph_url}/{account_id}",
        params={"fields": "username,name,biography,website,followers_count"},
        headers=headers,
    )
    request(
        "POST",
        f"{graph_url}/{account_id}/subscribed_apps",
        data={"subscribed_fields": "messages,messaging_postbacks"},
        headers=headers,
    )
    deadlines = [int(debug.get(field) or 0) for field in ("expires_at", "data_access_expires_at")]
    expiry = min((deadline for deadline in deadlines if deadline > 0), default=None)
    return Credentials(
        account_id,
        profile.get("username", account_id),
        token,
        datetime.fromtimestamp(expiry, UTC) if expiry else datetime.max.replace(tzinfo=UTC),
        meta_authorizer_id=str(debug.get("user_id") or ""),
        profile={
            "unified_login": True,
            **{field: profile.get(field, "") for field in ("name", "biography", "website")},
            "followers_count": profile.get("followers_count", 0),
        },
    )
