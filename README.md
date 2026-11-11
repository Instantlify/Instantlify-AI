# Instantlify

A multi-tenant platform that automates sales conversations across Instagram, WhatsApp, Messenger and Telegram with a visual flow builder and an autonomous AI sales agent: unified inbox, CRM, bookings, in-chat payments, funnel analytics, A/B tests, a template marketplace, content calendar, link-in-bio pages, a public API with webhooks, and white-label agency workspaces.

Everything runs locally with fake providers and no third-party keys. Live delivery on each channel, real bookings and real payments require the corresponding credentials and (for Meta) app review — see [docs/META_REVIEW.md](docs/META_REVIEW.md).

## Run locally

Requirements: Docker Desktop with Linux containers, Docker Compose v2, and approximately 4 GB of available container memory. No Meta, LLM, or Stripe keys are required.

Windows PowerShell, from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
docker compose up --build -d --wait --wait-timeout 240
```

macOS/Linux:

```sh
sh scripts/bootstrap.sh
docker compose up --build -d --wait --wait-timeout 240
```

Open [Instantlify](http://localhost:3000) for the public homepage, product information and current pricing. Choose **Get started** to create an account (password of at least 12 characters), or **Sign in** to return to your workspace. Authentication is at `/auth/`; existing invitation links remain supported. A good first tour with no external keys:

1. **Overview → Test connection setup** creates a local Instagram test channel.
2. **Automations → Create** opens the flow builder with a starter “comment *price* → DM with a button” flow; press **Publish**.
3. **Integrations → Simulate an inbound message** (kind *comment*, text containing “price”) fires the flow; the reply appears in **Inbox** within a few seconds.
4. **AI agent**: tick *Use the local test provider*, enable the agent, paste some FAQ text. In the inbox, switch **AI replies** on for the conversation and simulate a DM.
5. **Analytics** shows the funnel; **Link in bio**, **Payments** (offers), **Content**, **Templates**, **Team** (invites) and **Settings** (branding, agency clients, export/delete) round out the product.

The bootstrap scripts create an ignored `.env` with cryptographically random secrets and preserve existing configuration. The migration job runs before the web and worker services. PostgreSQL's `vector` extension is enabled by migration. The workspace dashboard reports actual database/cache/worker health, with the worker heartbeat produced every 30 seconds by Celery Beat. Wait up to 60 seconds after a cold start for it to turn green.

| Service | Local address | Notes |
| --- | --- | --- |
| Next.js | http://localhost:3000 | Same-origin proxy to Django |
| Django liveness | http://localhost:8000/health/live/ | Web process health |
| Full readiness | http://localhost:8000/health/ready/ | DB + Redis + Beat/worker heartbeat |
| Flower | http://localhost:5555 | Username `local`; password is in the ignored `.env` under `FLOWER_BASIC_AUTH` |
| PostgreSQL / Redis | Compose network only | No host ports exposed |

`docker compose stop` preserves everything. `docker compose down` removes containers and preserves volumes. Do not remove volumes unless you intend to delete local data.

## What is implemented

- **Channels**: Instagram (Meta OAuth, long-lived tokens, proactive refresh, private comment replies, buttons, content publishing), WhatsApp, Messenger and Telegram behind one `ChannelAdapter`; signed, deduplicated, durably queued webhooks; per-account rate limits with backoff; 24-hour window rules.
- **Automations**: React Flow builder (messages, buttons, wait, condition, delay, end), keyword triggers on comments/DMs/story replies/live comments, resumable persistent execution, per-lead cooldown, export/import and a community template marketplace.
- **AI agent**: BYO OpenAI key (encrypted), RAG over uploaded docs in pgvector, LangGraph turn with triage → sales stage machine → bounded tool loop; guarded tools (calendar check, booking with customer confirmation code, CRM updates, voice notes, payment links from configured offers, human handoff); full audit of runs, tool calls and usage; voice-note transcription.
- **Inbox & CRM**: live WebSocket inbox across channels, assignment, role-based visibility, internal notes, lead stages/tags/fields, AI segmentation with Slack hot-lead alerts, human handoff state, merge, and integrations (Google Calendar, Cal.com, Airtable, Notion, GoHighLevel, Attio, Slack, ElevenLabs, Stripe).
- **Growth**: funnel analytics (comment → DM → triggered → replied → booked → paid, per automation/channel, revenue), A/B experiments with auto-promotion, sentiment/urgency handoff, in-chat payments on the workspace's own Stripe, content calendar, link-in-bio pages with click tracking.
- **Platform**: seat/channel/usage plans with Stripe subscriptions and metered AI usage, team invitations, public API keys + signed outbound webhooks (Zapier/n8n/Make), white-label branding and agency client workspaces, GDPR export/delete, retention, Sentry with scrubbing, structured logs, backlog alerts.

### Foundation

- Django 5.2 LTS, DRF, PostgreSQL 17 + pgvector, Celery/Redis/Beat/Flower, Next.js 16 + TypeScript.
- `apps/tenants`, `channels`, `automations`, `agents`, `crm`, `billing`, `dashboard_api` package boundaries. Future-phase apps intentionally contain no speculative business models.
- Custom Django user, case-insensitive unique email, workspace, membership with owner/admin/agent roles and database constraints.
- Cookie/session authentication for the browser, explicit CSRF protection including signup/login, and short-lived JWT access tokens with rotating/revocable refresh tokens for API clients.
- Explicitly scoped tenant managers, per-request membership authorization, tenant-scoped audit events, and an idempotent transactional outbox.
- Authenticated encryption of channel credentials with a separately managed key ring. Tokens never appear in serializers, object representations, log messages, or queue arguments.
- A provider-neutral adapter interface, Instagram parsing boundary, fake adapter, hashed/expiring/single-use OAuth state, and a local-only connection test. Live OAuth is disabled until Phase 1.
- Signature-verification tests and a tested, pure one-step automation safety kernel before any live webhook or execution endpoint is exposed.
- Responsive onboarding, workspace overview, workspace switching, settings, team role management, and audit history. Counts and status come from the API.
- CI for linting, formatting, migrations, PostgreSQL tests, frontend build/type-check, Compose readiness, and browser onboarding.

## Tests and development

Python 3.12 and [uv](https://docs.astral.sh/uv/) are used for local backend work:

```sh
cd backend
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run --settings=config.settings.test
uv run pytest -q
```

Without `DATABASE_URL`, unit tests use SQLite; the pgvector check is deliberately skipped. **CI runs the same tests against PostgreSQL with pgvector**, including database constraints. SQLite is not a supported application deployment database and does not verify PostgreSQL locking behavior.

Run the full PostgreSQL suite using the local Compose network (no host database port or local Python needed):

```sh
docker compose --profile test run --build --rm test
```

```sh
cd frontend
npm ci
npm run lint
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

The browser test expects the Compose app running on `http://127.0.0.1:3000`; override with `E2E_BASE_URL`. It signs up, creates a workspace and test channel, publishes an automation, fires it with a simulated comment, replies from the inbox, enables the test AI agent, checks analytics, publishes a bio page, creates an offer and an invitation, and verifies the mobile layout. It writes real local data and never contacts Meta.

For frontend hot reload against Compose: stop the frontend container with `docker compose stop frontend`, then run `npm run dev` from `frontend/`. The default local proxy target is `http://127.0.0.1:8000`. Set `BACKEND_INTERNAL_URL` before starting/building if you change the backend address. This address is embedded at build time in standalone output.

## Deploying

For `instantlify.com`, the confirmed support mailbox, and separate staging and
production environment files, see [domain setup](docs/DOMAIN_SETUP.md).

`compose.yaml` on its own is the local stack: loopback ports, no edge, no certificates,
no backups. Production adds those through an overlay:

```sh
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```

The overlay puts Caddy in front as the only service the internet reaches, switches the
Django services to production settings, drops Flower behind the `debug` profile, and
runs a `backup` service that keeps timestamped `pg_dump`s in the `backups` volume.

Set these in the environment before the first deploy, on top of `.env`:

| Variable | Why |
| --- | --- |
| `APP_DOMAIN` | Public app hostname Caddy gets a certificate for |
| `PLATFORM_ADMIN_HOST` | Console hostname; must match Django's setting and differ from the app |
| `ACME_EMAIL` | Certificate expiry notices |
| `TRUSTED_PROXY_DEPTH` | Proxies in front of Django. `1` behind this Caddy; production refuses to start at `0` |
| `NEMIO_PRIVACY_URL`, `NEMIO_TERMS_URL`, `NEMIO_SUPPORT_EMAIL` | Published policies and support contact; the frontend must be rebuilt after a change |

**A backup you have not restored is not a backup.** Copy dumps off the host, and
rehearse a restore before you need one:

```sh
docker compose -f compose.yaml -f compose.prod.yaml stop backend worker beat
docker compose -f compose.yaml -f compose.prod.yaml run --rm   -e CONFIRM_RESTORE=yes backup /restore.sh /backups/nemio-<stamp>.sql.gz
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

`restore.sh` drops and recreates the schema, so everything written since that dump is
lost; it refuses to run without `CONFIRM_RESTORE=yes`. The database dump does not
contain `FIELD_ENCRYPTION_KEYS`: restoring without those keys leaves every stored
credential undecryptable, so back the key ring up separately.

## Operational notes

- `.env.example` and [environment documentation](docs/ENVIRONMENT.md) enumerate configuration. Local Compose is **not** a public production deployment: use production settings, TLS, a trusted ingress, private data services, managed secrets and backups before accepting customers.
- Only the single Beat service should schedule periodic jobs. Multiple workers are supported; replaying an outbox job produces one provisioning event.
- The outbox poller passes only `(workspace_id, event_id)` into Redis. A broker outage leaves durable events pending for the next poll. Processing is locked and committed atomically. The five-second interval is acceptable for workspace setup; Phase 1 webhooks need a prompt dispatcher plus the same durable recovery strategy.
- Browser logout terminates the browser session. API clients must explicitly revoke their refresh token; an issued access token remains valid for at most five minutes. Browser tokens are not stored in localStorage.
- OAuth callback access logs must omit query strings. The Django JSON formatter intentionally discards arbitrary message and exception contents to prevent credential leakage. Local Gunicorn access logging is disabled. The production ingress must apply the same policy.
- Refresh-token rows are cleaned daily. Define business-data retention in the compliance increment; a database backup is not a substitute for credential-key backup.

See [architectural decisions](DECISIONS.md), [API reference](docs/API.md), [public API and webhooks](docs/PUBLIC_API.md), [Meta external gate](docs/META_REVIEW.md), [phase roadmap](docs/ROADMAP.md) and [implementation status](docs/IMPLEMENTATION_STATUS.md).
