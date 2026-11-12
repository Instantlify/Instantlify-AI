"""Sliding browser sessions driven by explicit user activity, never background polls."""

import ipaddress
from datetime import UTC, datetime
from time import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .client_ip import client_ip
from .models import BrowserSession, User

ACTIVITY_KEY = "last_user_activity"
VERSION_KEY = "auth_session_version"


def device_label(agent):
    agent = agent[:500]
    browser = next(
        (
            name
            for marker, name in [
                ("Edg/", "Edge"),
                ("OPR/", "Opera"),
                ("Firefox/", "Firefox"),
                ("Chrome/", "Chrome"),
                ("Safari/", "Safari"),
            ]
            if marker in agent
        ),
        "Browser",
    )
    system = next(
        (
            name
            for marker, name in [
                ("iPhone", "iPhone"),
                ("iPad", "iPad"),
                ("Android", "Android"),
                ("Windows", "Windows"),
                ("Macintosh", "macOS"),
                ("Linux", "Linux"),
            ]
            if marker in agent
        ),
        "Unknown device",
    )
    return f"{browser} on {system}"


def session_record(request, user, timestamp):
    key = request.session.session_key
    if not key:
        request.session.save()
        key = request.session.session_key
    try:
        address = str(ipaddress.ip_address(client_ip(request)))
    except ValueError:
        address = None
    record, _ = BrowserSession.objects.get_or_create(
        session_key=key,
        user=user,
        defaults={
            "device": device_label(request.META.get("HTTP_USER_AGENT", "")),
            "ip_address": address,
            "last_activity": datetime.fromtimestamp(timestamp, UTC),
            "expires_at": datetime.fromtimestamp(timestamp + settings.SESSION_COOKIE_AGE, UTC),
        },
    )
    return record


def touch_session(request, timestamp=None):
    timestamp = time() if timestamp is None else timestamp
    request.session[ACTIVITY_KEY] = timestamp
    request.session.set_expiry(datetime.fromtimestamp(timestamp + settings.SESSION_COOKIE_AGE, UTC))
    if request.user.is_authenticated:
        record = session_record(request, request.user, timestamp)
        if not record.revoked_at:
            BrowserSession.objects.filter(pk=record.pk, revoked_at__isnull=True).update(
                last_activity=datetime.fromtimestamp(timestamp, UTC),
                expires_at=datetime.fromtimestamp(timestamp + settings.SESSION_COOKIE_AGE, UTC),
            )


def on_login(sender, request, user, **kwargs):
    request.user = user
    request.session[VERSION_KEY] = user.session_version
    touch_session(request)


def on_logout(sender, request, user, **kwargs):
    if request and request.session.session_key:
        BrowserSession.objects.filter(
            session_key=request.session.session_key, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())


class IdleSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            last_activity = request.session.get(ACTIVITY_KEY)
            record = session_record(request, request.user, last_activity or time())
            if (
                record.revoked_at
                or request.session.get(VERSION_KEY, 0) != request.user.session_version
            ):
                logout(request)
            elif last_activity is None:
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


class BrowserSessionListView(APIView):
    authentication_classes = [SessionAuthentication]

    def get(self, request):
        rows = BrowserSession.objects.filter(
            user=request.user, revoked_at__isnull=True, expires_at__gt=timezone.now()
        )[:100]
        stored = {
            item.session_key: item
            for item in Session.objects.filter(
                session_key__in=[row.session_key for row in rows], expire_date__gt=timezone.now()
            )
        }
        results = []
        for row in rows:
            session = stored.get(row.session_key)
            data = session.get_decoded() if session else {}
            if (
                str(data.get("_auth_user_id")) != str(request.user.pk)
                or data.get("_auth_user_hash") != request.user.get_session_auth_hash()
            ):
                continue
            if data.get(VERSION_KEY, 0) != request.user.session_version:
                continue
            results.append(
                {
                    "id": str(row.pk),
                    "device": row.device,
                    "ip_address": row.ip_address,
                    "created_at": row.created_at,
                    "last_activity": row.last_activity,
                    "expires_at": row.expires_at,
                    "current": row.session_key == request.session.session_key,
                }
            )
        return Response({"results": results})


class BrowserSessionRevokeView(APIView):
    authentication_classes = [SessionAuthentication]

    @transaction.atomic
    def delete(self, request, pk):
        record = get_object_or_404(
            BrowserSession.objects.select_for_update(), pk=pk, user=request.user
        )
        record.revoked_at = timezone.now()
        record.save(update_fields=["revoked_at"])
        current = record.session_key == request.session.session_key
        Session.objects.filter(session_key=record.session_key).delete()
        if current:
            logout(request)
        return Response(status=204)


class BrowserSessionRevokeAllView(APIView):
    authentication_classes = [SessionAuthentication]

    @transaction.atomic
    def post(self, request):
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        user = User.objects.select_for_update().get(pk=request.user.pk)
        User.objects.filter(pk=user.pk).update(session_version=F("session_version") + 1)
        keys = list(BrowserSession.objects.filter(user=user).values_list("session_key", flat=True))
        BrowserSession.objects.filter(user=user, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        Session.objects.filter(session_key__in=keys).delete()
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        logout(request)
        return Response(status=204)
