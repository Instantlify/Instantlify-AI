from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.db import models


def cipher():
    return MultiFernet([Fernet(key.strip().encode()) for key in settings.FIELD_ENCRYPTION_KEYS])


class EncryptedTextField(models.TextField):
    """Authenticated storage encryption with multi-key rotation; not for filtering."""

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        return cipher().decrypt(value.encode()).decode()

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        return cipher().encrypt(str(value).encode()).decode()
