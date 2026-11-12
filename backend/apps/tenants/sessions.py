"""Sliding browser sessions driven by explicit user activity, never background polls."""

from datetime import UTC, datetime
from time import time

from django.conf import settings
from django.contrib.auth import logout
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

ACTIVITY_KEY = "last_user_activity"


def touch_session(request, timestamp=None):
    timestamp = time() if timestamp is None else timestamp
    request.session[ACTIVITY_KEY] = timestamp
    request.session.set_expiry(datetime.fromtimestamp(timestamp + settings.SESSION_COOKIE_AGE, UTC))


def on_login(sender, request, user, **kwargs):
    touch_session(request)


class IdleSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            last_activity = request.session.get(ACTIVITY_KEY)
            if last_activity is None:
                # Bring sessions created before this policy under the new timeout.
                touch_session(request)
            elif time() - last_activity >= settings.SESSION_COOKIE_AGE:
                logout(request)
        return self.get_response(request)


class ActivitySerializer(serializers.Serializer):
    # A trailing heartbeat records when the interaction actually happened rather
    # than granting extra idle time because it was sent a few seconds later.
    inactive_for = serializers.FloatField(min_value=0, max_value=60, default=0)


class SessionActivityView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    # Keep session activity separate from the stricter sign-in attempt throttle.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "session_activity"

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"authenticated": False})
        return Response(
            {
                "authenticated": True,
                "idle_timeout": settings.SESSION_COOKIE_AGE,
                "remaining": max(
                    0, request.session[ACTIVITY_KEY] + settings.SESSION_COOKIE_AGE - time()
                ),
            }
        )

    def post(self, request):
        if not request.user.is_authenticated:
            raise NotAuthenticated("Your session has expired. Please sign in again.")
        serializer = ActivitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        timestamp = max(
            request.session[ACTIVITY_KEY], time() - serializer.validated_data["inactive_for"]
        )
        touch_session(request, timestamp)
        return self.get(request)
