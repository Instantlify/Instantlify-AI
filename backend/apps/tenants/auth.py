"""Authentication that honours `User.is_banned` on every path.

A ban has to hold at three points, and each needs its own hook:

- password sign-in (session login, JWT obtain, the ops console) goes through
  `authenticate()`, which asks the backend's `user_can_authenticate`;
- an existing session is re-resolved on every request through the backend's
  `get_user`, which asks the same question, so a banned user's open session turns
  anonymous on their next click;
- a bearer token is resolved by DRF's JWT class, which never consults the backend,
  so it gets its own check.
"""

from django.contrib.auth.backends import ModelBackend
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class BanAwareBackend(ModelBackend):
    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and not getattr(user, "is_banned", False)


class BanAwareJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if getattr(user, "is_banned", False):
            raise AuthenticationFailed("This account is suspended.", code="user_banned")
        if validated_token.get("session_version", 0) != user.session_version:
            raise AuthenticationFailed(
                "This login has been revoked. Please sign in again.", code="session_revoked"
            )
        return user


class VersionedTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["session_version"] = user.session_version
        return token
