import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.tenants.models import User
from apps.tenants.services import create_workspace


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="owner", email="owner@example.com", password="A-very-long-password42"
    )


@pytest.fixture
def workspace(user):
    return create_workspace(user, "Acme")


@pytest.fixture
def client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client
