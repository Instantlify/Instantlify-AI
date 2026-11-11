from django.test import Client, override_settings


@override_settings(
    ALLOWED_HOSTS=["staging.instantlify.com"],
    SECURE_SSL_REDIRECT=True,
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
)
def test_liveness_probe_uses_production_host_and_proxy_scheme():
    client = Client()
    assert client.get("/health/live/", HTTP_HOST="localhost").status_code == 400
    assert (
        client.get("/health/live/", HTTP_HOST="staging.instantlify.com").status_code == 301
    )
    response = client.get(
        "/health/live/",
        HTTP_HOST="staging.instantlify.com",
        HTTP_X_FORWARDED_PROTO="https",
    )
    assert response.status_code == 200
