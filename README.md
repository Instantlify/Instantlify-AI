# Nemio

A multi-tenant sales conversation platform, built in shippable phases. This increment implements **Phase 0: the platform foundation**. Live messaging, automation authoring, autonomous agents, CRM integrations, and billing remain later increments; they are not simulated as finished product features.

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

Open [Nemio](http://localhost:3000). Create an account with a password of at least 12 characters, create a workspace, sign out, and sign back in. Your workspace persists. Use the workspace switcher to create and navigate multiple workspaces. Workspace owners can rename their workspace, see its audit trail, and manage existing members' admin/agent roles. Invitations are a later team feature.

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

The browser test expects the Compose app running on `http://127.0.0.1:3000`; override with `E2E_BASE_URL`. It creates an isolated test account, workspace and local channel connection, updates settings, logs out, and logs in. The test writes real local data. It never contacts Meta.

For frontend hot reload against Compose: stop the frontend container with `docker compose stop frontend`, then run `npm run dev` from `frontend/`. The default local proxy target is `http://127.0.0.1:8000`. Set `BACKEND_INTERNAL_URL` before starting/building if you change the backend address. This address is embedded at build time in standalone output.

## Operational notes

- `.env.example` and [environment documentation](docs/ENVIRONMENT.md) enumerate configuration. Local Compose is **not** a public production deployment: use production settings, TLS, a trusted ingress, private data services, managed secrets and backups before accepting customers.
- Only the single Beat service should schedule periodic jobs. Multiple workers are supported; replaying an outbox job produces one provisioning event.
- The outbox poller passes only `(workspace_id, event_id)` into Redis. A broker outage leaves durable events pending for the next poll. Processing is locked and committed atomically. The five-second interval is acceptable for workspace setup; Phase 1 webhooks need a prompt dispatcher plus the same durable recovery strategy.
- Browser logout terminates the browser session. API clients must explicitly revoke their refresh token; an issued access token remains valid for at most five minutes. Browser tokens are not stored in localStorage.
- OAuth callback access logs must omit query strings. The Django JSON formatter intentionally discards arbitrary message and exception contents to prevent credential leakage. Local Gunicorn access logging is disabled. The production ingress must apply the same policy.
- Refresh-token rows are cleaned daily. Define business-data retention in the compliance increment; a database backup is not a substitute for credential-key backup.

See [architectural decisions](DECISIONS.md), [API reference](docs/API.md), [Meta external gate](docs/META_REVIEW.md), and [phase roadmap](docs/ROADMAP.md).
