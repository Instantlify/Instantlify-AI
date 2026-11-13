# Browser checks before a PR and before production

Run the full Playwright suite locally before pushing changes and opening a PR.
The pipeline keeps a smaller browser gate for everyday development:

| Trigger | Browser coverage |
| --- | --- |
| PR targeting `dev` | Smoke suite |
| Push to `dev` | Smoke suite |
| PR targeting `main` | Full suite |
| Push to `main` | Full suite before production image publishing/deployment |

Backend tests, frontend lint/types/format/build, deployment-image checks and image
publishing dependencies are unchanged. Passing smoke checks does not certify that
the full suite was run locally; the pre-push full run is a developer responsibility.

## Local full run

Start Docker Desktop/your local Docker engine. From the repository root, bootstrap
local configuration if necessary (`scripts/bootstrap.ps1` on Windows or
`sh scripts/bootstrap.sh`), then:

```sh
docker compose up --build -d --wait --wait-timeout 240
npm ci --prefix frontend
cd frontend
npx playwright install chromium
npm run test:e2e:full
```

Use only the local development stack and its fake/test adapters. Do not point the
suite at production: it creates and modifies test accounts/workspaces. The real
onboarding journey requires Docker Compose on localhost. Leave `E2E_BASE_URL` unset
for the full verification; setting it deliberately skips that real-backend journey.
Resolve failures before pushing. `npm run test:e2e` remains an alias for the full
suite. The existing teardown removes test accounts from the local Compose backend.

## Quick smoke run

With the same local stack running:

```sh
cd frontend
npm run test:e2e:smoke
npm run test:e2e:smoke -- --list
```

The `@smoke` tag currently selects seven tests: homepage/signup navigation, mobile
sign-in entry, password recovery, workspace navigation, and three real-backend
journey steps for signup/onboarding, workspace rename and desktop/mobile sign-out
and sign-in. Keep all three onboarding steps tagged together: they share a serial
account/session and the last step checks the renamed workspace. Do not tag a later
step without its setup dependencies.

CI still starts the Compose stack and checks DB/cache/worker readiness. Reducing
browser coverage saves execution time, not all container build/startup time.
Failed runs retain the existing artifact upload behavior; GitHub storage quota
remains an account/billing issue and is not bypassed by this change.
