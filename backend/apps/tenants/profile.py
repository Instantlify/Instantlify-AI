import base64
import hashlib

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ProfilePhoto


def photo_url(user):
    digest = ProfilePhoto.objects.filter(user=user).values_list("digest", flat=True).first()
    return f"/api/auth/photo/?v={digest}" if digest else ""


class ProfileSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(max_length=254, required=False)
    photo = serializers.FileField(required=False, write_only=True)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_photo(self, value):
        if not 0 < value.size <= 2 * 1024 * 1024:
            raise serializers.ValidationError("Choose an image up to 2 MB.")
        data = value.read()
        kind = (
            "image/png"
            if data.startswith(b"\x89PNG\r\n\x1a\n")
            else "image/jpeg"
            if data.startswith(b"\xff\xd8\xff")
            else "image/gif"
            if data.startswith((b"GIF87a", b"GIF89a"))
            else "image/webp"
            if data.startswith(b"RIFF") and data[8:12] == b"WEBP"
            else ""
        )
        if not kind:
            raise serializers.ValidationError("Choose a PNG, JPG, GIF or WebP image.")
        return {
            "data": base64.b64encode(data).decode(),
            "content_type": kind,
            "digest": hashlib.sha256(data).hexdigest(),
        }


class ProfilePhotoView(APIView):
    def get(self, request):
        photo = get_object_or_404(ProfilePhoto, user=request.user)
        response = HttpResponse(base64.b64decode(photo.data), content_type=photo.content_type)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def delete(self, request):
        ProfilePhoto.objects.filter(user=request.user).delete()
        return Response(status=204)
