"""The caller's real address, for code that rate-limits or allow-lists by IP.

`REMOTE_ADDR` is the address of whoever opened the TCP connection. Behind the edge
proxy in `deploy/` that is always the proxy itself, so every request in production
looks like it comes from one machine: an IP allow-list then matches everyone or
no one, and a per-IP lockout becomes one global bucket.

`X-Forwarded-For` carries the chain instead, but each hop *appends* to whatever
arrived, so the left-hand entries are supplied by the caller and are worth nothing.
Only the last `TRUSTED_PROXY_DEPTH` entries were written by infrastructure we run.
Counting from the right is what makes the value unspoofable, and it is the same
rule DRF's `NUM_PROXIES` applies to throttle keys, so both agree on who is calling.

This assumes only the edge proxy can reach Django. Anyone who can connect to the
container directly writes the whole header themselves; that is a network boundary,
not something this function can check.
"""

from django.conf import settings


def client_ip(request):
    depth = getattr(settings, "TRUSTED_PROXY_DEPTH", 0)
    remote_addr = request.META.get("REMOTE_ADDR", "")
    if depth < 1:
        return remote_addr
    chain = [part.strip() for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")]
    chain = [part for part in chain if part]
    if not chain:
        # Nothing was forwarded, so this is a direct peer rather than a proxied client.
        return remote_addr
    return chain[-min(depth, len(chain))]
