# Environment and secret inventory

All settings load from process environment. Docker Compose injects the ignored root `.env`; Django does not silently load arbitrary dotenv files. Bootstrap fills the example with random **local-only** secrets. Do not commit `.env`, copy production credentials into test runs, or print resolved Compose config into logs.

| Variable | Required | Secret | Purpose |
| --- | --- | --- | --- |
| `DJANGO_SETTINGS_MODULE` | Yes in deployment | No | `config.settings.local`, `.staging`, or `.production` |
| `DJANGO_SECRET_KEY` | Yes | Yes | Random Django signing key, at least 50 characters in production |
| `FIELD_ENCRYPTION_KEYS` | Yes | Yes | Comma-separated Fernet keys; active write key first, old read keys afterward |
| `DATABASE_URL` | Yes | Yes | PostgreSQL DSN; use TLS for managed remote databases |
| `POSTGRES_DB` | Local Compose | No | DB name |
| `POSTGRES_USER` | Local Compose | No | DB bootstrap role |
| `POSTGRES_PASSWORD` | Local Compose | Yes | Must match `DATABASE_URL` |
| `REDIS_URL` | Deployment | Potentially | Cache DB, default `redis://redis:6379/0`; auth URLs are secrets |
| `CELERY_BROKER_URL` | Deployment | Potentially | Queue DB, default Redis DB 1 |
| `CELERY_RESULT_BACKEND` | Deployment | Potentially | Short-lived task results, default Redis DB 2 |
| `ALLOWED_HOSTS` | Deployment | No | Comma-separated actual hosts; production rejects wildcard/localhost |
| `CSRF_TRUSTED_ORIGINS` | Deployment | No | Exact browser origins including scheme and local port |
| `BACKEND_INTERNAL_URL` | Frontend build | No | Default Compose target `http://backend:8000`; rebuild frontend after changing |
| `CHANNEL_ADAPTER_MODE` | Yes | No | `fake` only in local/test; `disabled` in staging/prod until Phase 1 |
| `FLOWER_BASIC_AUTH` | Local Flower | Yes | `username:password`; random bootstrap password, no public exposure |
| `META_APP_ID` | Phase 1 | No | App ID, presently unused by local fake |
| `META_APP_SECRET` | Phase 1 | Yes | OAuth/signature verification secret |
| `META_REDIRECT_URI` | Phase 1 | No | Exact registered HTTPS callback; local fake uses relative callback |
| `META_CALLS_PER_HOUR` | No | No | Outbound calls per hour per Instagram account (default 200) |
| `WHATSAPP_CALLS_PER_HOUR` / `TELEGRAM_CALLS_PER_HOUR` | No | No | Per-connection outbound budgets (defaults 3600 / 1800) |
| `META_APP_CALLS_PER_HOUR` | No | No | Optional app-wide Meta ceiling across all tenants; `0` disables |
| `META_SCOPES` | Phase 1 | No | Permission list for selected Instagram login product; confirm during live implementation |

Meta webhook verification token, pinned Graph API version, provider key fields, Stripe keys/webhook secret, calendar OAuth client credentials, ElevenLabs credentials and Sentry configuration will be added with their respective integrations. They are not required or read by Phase 0.

## Production differences

Production settings force secure cookies, HTTPS redirects, HSTS, `DEBUG=False`, and explicit allowed hosts. Staging keeps secure cookies/HTTPS but uses a shorter HSTS duration. The reverse proxy must be trusted, must overwrite `X-Forwarded-Proto`, and must be the only route to Django. Do not let arbitrary public clients reach a backend that trusts forwarding headers.

Before a public deployment: configure actual HTTPS origins/hosts, set `CHANNEL_ADAPTER_MODE=disabled`, use private authenticated Redis and PostgreSQL, separate migration/runtime DB roles, provision keys via a secrets manager, configure restore-tested backups, and run `python manage.py check --deploy --settings=config.settings.production`. The local Compose topology is a developer environment.

DRF throttles reduce accidental abuse and basic brute-force attempts. They are not a hard distributed security boundary; the ingress must enforce request/body/connection limits and an authentication rate policy. Avoid URL query strings in access logs, particularly on `/api/meta/callback/`.
