"""Error tracking that never ships customer content or credentials."""

import os

SCRUBBED_KEYS = {"authorization", "cookie", "x-api-key", "x-hub-signature-256", "stripe-signature"}


def scrub(event, hint):
    request = event.get("request") or {}
    request.pop("data", None)
    request.pop("cookies", None)
    request.pop("query_string", None)
    headers = request.get("headers") or {}
    for key in list(headers):
        if key.lower() in SCRUBBED_KEYS:
            headers[key] = "[filtered]"
    # URLs may carry OAuth codes or invite tokens.
    if "url" in request:
        request["url"] = request["url"].split("?")[0]
    event.pop("user", None)
    for exception in (event.get("exception") or {}).get("values", []):
        for frame in (exception.get("stacktrace") or {}).get("frames", []):
            frame.pop("vars", None)
    return event


def configure_sentry():
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "local"),
        release=os.environ.get("APP_RELEASE") or None,
        integrations=[DjangoIntegration(), CeleryIntegration(monitor_beat_tasks=True)],
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
        before_send=scrub,
    )
    return True
