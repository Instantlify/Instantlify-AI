import hashlib
import hmac
import re


def verify_meta_signature(body: bytes, header: str | None, secret: str) -> bool:
    if not secret or not header or not re.fullmatch(r"sha256=[0-9a-f]{64}", header):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)
