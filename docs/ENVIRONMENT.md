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
| `MESSENGER_CALLS_PER_HOUR` | No | No | Per-Page outbound budget (default 3600) |
| `WHATSAPP_APP_SECRET` / `MESSENGER_APP_SECRET` | If separate Meta apps | Yes | Webhook signature secrets; default to `META_APP_SECRET` |
| `META_WEBHOOK_VERIFY_TOKEN` | Phase 1 | Yes | Meta webhook subscription challenge token |
| `META_API_VERSION` | No | No | Graph API version, default `v23.0` |
| `PUBLIC_APP_URL` | Deployment | No | Public HTTPS origin used in invite links, voice media, checkout return URLs and Telegram webhooks |
| `ALLOW_TEST_CHANNELS` | Local testing | No | Default `false`. Set `true` alongside `CHANNEL_ADAPTER_MODE=live` to create explicit simulated channels and simulate inbound messages without platform credentials. Test connections always use fake delivery; non-test connections still require real credentials. Platform support AI stays live. Disabled channel mode continues to block test connections. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Calendar | Yes | Google Calendar hosted sign-in and token refresh |
| `SLACK_CLIENT_ID` / `SLACK_CLIENT_SECRET` | Slack | Yes | Slack app for the hosted "Add to Slack" install (`chat:write`, `incoming-webhook`) |
| `INTEGRATION_REDIRECT_BASE` | Hosted sign-in | No | Default `PUBLIC_APP_URL/api/integrations/callback/`; register `<base>google_calendar/` and `<base>slack/` with each provider |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Platform billing | Yes | Nemio's own subscriptions and metered AI usage |
| `STRIPE_PRICES` | Bootstrap only | No | Legacy JSON `{plan: {base, meter}}`; copied onto the monthly `PlanPrice` rows by the plans data migration. Prices now live in the database |
| `PLATFORM_OPENAI_API_KEY` | Prepaid credits | Yes | Nemio's own OpenAI key, used for every workspace on `platform_credits` billing |
| `PLATFORM_AI_MODEL` | Platform AI | No | OpenAI model used by Nemio support chat and business classification; defaults to `gpt-5`. Must be available to the key's project. Independent of workspace agents' model settings. Support knowledge search/indexing also needs `text-embedding-3-small` access; an empty or unindexed support knowledge base skips search. |
| `PLATFORM_GEMINI_MODEL` | Provider health | No | Gemini model for the admin provider health test; defaults to `gemini-3.5-flash-lite`. Also offered in the assistant model catalog. Workspace assistants use the model selected in their own settings. |
| `PLATFORM_ANTHROPIC_API_KEY` / `PLATFORM_GEMINI_API_KEY` / `PLATFORM_XAI_API_KEY` | For those providers | Yes | Nemio's key for agents on `platform_credits` whose provider (or fallback provider) is Anthropic, Gemini or xAI. Knowledge-base embeddings always use `PLATFORM_OPENAI_API_KEY` |
| `PLATFORM_<PROVIDER>_API_KEY_<LABEL>` | No | Yes | Extra named keys; each gets its own on-demand health card in the console. Not used by the agent runtime |
| `UPTIME_PROBE_URL` | No | No | Public readiness URL (e.g. `https://app.nemio.ai/health/ready/`) probed every minute through DNS, TLS and the proxy. Unset: the ingress check is skipped |
| `UPTIME_LATENCY_MS` | No | No | Default `2500`; a slower ingress response counts as a failure |
| `ALERT_WEBHOOK_URL` | No | Yes | Slack-compatible incoming webhook (JSON `text`) for DOWN/RESOLVED pages |
| `PAGERDUTY_ROUTING_KEY` | No | Yes | PagerDuty Events API v2 key; incidents trigger and resolve by check |
| `EMAIL_HOST` | Production | No | SMTP host for transactional email. Production refuses to boot without it; locally mail prints to the console |
| `EMAIL_PORT` / `EMAIL_USE_TLS` | No | No | Default `587` / `true` |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | With SMTP auth | Yes | SMTP credentials |
| `DEFAULT_FROM_EMAIL` | Production | No | Sender, e.g. `Nemio <no-reply@nemio.app>` |
| `STRIPE_TRIAL_DAYS` | No | No | Trial days on a workspace's first subscription (default 3; 0 disables) |
| `DEFAULT_PLAN_SLUG` | No | No | Plan a workspace is on before subscribing. `free` in base settings, `dev` (unlimited) in local settings |
| `STRIPE_METER_EVENT_NAME` | No | No | Meter event name, default `ai_messages` |
| `MARKETPLACE_FEE_PERCENT` | Marketplace | No | Platform share of paid template sales (default 15); needs `STRIPE_SECRET_KEY` and the platform webhook to receive `checkout.session.*` events |
| `PUBLIC_API_RATE` | No | No | Per-API-key throttle, default `600/min` |
| `SENTRY_DSN` | Production | Yes | Enables Sentry with request bodies, cookies, auth headers, query strings and local variables scrubbed |
| `SENTRY_ENVIRONMENT` / `SENTRY_TRACES_SAMPLE_RATE` / `APP_RELEASE` | No | No | Sentry tagging and tracing |
| `RETENTION_DAYS` | No | No | Customer payload retention (default 90) |
| `NEXT_PUBLIC_WS_URL` | Frontend | No | WebSocket origin for the live inbox (local default `ws://localhost:8000`); behind one domain in production the same-origin default applies |
| `META_SCOPES` | Phase 1 | No | Permission list for selected Instagram login product; confirm during live implementation |

Tenant-owned credentials (LLM keys, ElevenLabs, calendar, CRM, Slack and each workspace's Stripe keys for in-chat payments) are entered in the app and stored encrypted; they are never environment variables.

For local Stripe subscription testing, use `tools/stripe_local.py` with the backend virtualenv.
It reads the test key from the ignored root `.env`, configures the Stripe CLI listener secret
without displaying it, and forwards to the local backend. Recreate the backend after the
secret is updated. See [the local verification procedure](LIVE_PROVIDER_VERIFICATION.md#repeat-the-local-stripe-check).

## Production differences

Production settings force secure cookies, HTTPS redirects, HSTS, `DEBUG=False`, and explicit allowed hosts. Staging keeps secure cookies/HTTPS but uses a shorter HSTS duration. The reverse proxy must be trusted, must overwrite `X-Forwarded-Proto`, and must be the only route to Django. Do not let arbitrary public clients reach a backend that trusts forwarding headers.

Before a public deployment: configure actual HTTPS origins/hosts, set `CHANNEL_ADAPTER_MODE=disabled`, use private authenticated Redis and PostgreSQL, separate migration/runtime DB roles, provision keys via a secrets manager, configure restore-tested backups, and run `python manage.py check --deploy --settings=config.settings.production`. The local Compose topology is a developer environment.

DRF throttles reduce accidental abuse and basic brute-force attempts. They are not a hard distributed security boundary; the ingress must enforce request/body/connection limits and an authentication rate policy. Avoid URL query strings in access logs, particularly on `/api/meta/callback/`.
