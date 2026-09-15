# Phase 0 verification

Verified locally on 2026-09-14. No live provider keys were used and no external accounts were connected.

| Gate | Result | Evidence |
| --- | --- | --- |
| Django API/safety suite on PostgreSQL | PASS | 41 tests passed in the Compose test container, with no warnings or skips |
| pgvector | PASS | Migration enables `vector`; test verifies the extension is installed in PostgreSQL |
| Tenant isolation and roles | PASS | Foreign-workspace reads return 404; agent writes/audit access rejected; owner role constraints tested |
| Authentication | PASS | Password validation, email uniqueness, CSRF enforcement, browser session flow, JWT rotation and revocation |
| Credential/OAuth safety | PASS | Ciphertext at rest, no credential serialization, key-ring decryption, expiring user-bound single-use state |
| Async reliability | PASS | Concurrent delivery produces one audit effect; foreign tenant/job IDs do nothing; real worker drained browser-created setup jobs |
| Signature and automation contracts | PASS | Exact-body HMAC verification; malformed/missing/wrong-secret rejection; wait/resume, one-step behavior, invalid graph and cycle budget |
| Browser onboarding | PASS | Chromium: signup → create workspace → local OAuth test → rename → logout → login; desktop and mobile |
| Responsive layout | PASS | Desktop and 390px mobile screenshots inspected; no horizontal overflow; sign-out reachable on both |
| Frontend | PASS | ESLint, TypeScript and Next.js production build; Prettier formatting gate |
| Django configuration | PASS | No pending model migrations; Django system checks and production `check --deploy` report no issues |
| Compose | PASS | PostgreSQL, Redis, web, worker, beat, frontend and Flower boot; migration job exits successfully |
| Full readiness | PASS | `database=true`, `redis=true`, `worker=true` from `/health/ready/` |
| Remote GitHub CI | NOT RUN | Workflow is included; repository/remote push is outside this local build |
| Live Meta integration/review | NOT RUN | Phase 1 external gate, tracked in `META_REVIEW.md` |

The browser test found a short-screen sidebar overflow that made sign-out unreachable. The sidebar now scrolls, and mobile has its own sign-out action. A PostgreSQL test teardown warning identified an open connection in the concurrency test; its worker threads now close their connections explicitly. Both checks passed after correction.

Production checks were run against production settings with synthetic validation-only secrets/hostnames. This validates the configuration rules, not a public TLS deployment or operational policy audit. The running Compose application uses local settings and generated local secrets.

## Reproduce

From the repository root:

```sh
docker compose up --build -d --wait --wait-timeout 240
docker compose --profile test run --build --rm test
```

From `backend/`:

```sh
uv run ruff check .
uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

From `frontend/`:

```sh
npm run lint
npm run typecheck
npm run format:check
npm run build
npm run test:e2e
```

The E2E test creates clearly named test accounts/workspaces in the local application database. Screenshots are generated under the ignored `frontend/test-results/` directory. Test traces may contain test-session cookies; do not publish them as public artifacts.
