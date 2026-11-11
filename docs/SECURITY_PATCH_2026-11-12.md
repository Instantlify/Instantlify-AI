# Container security patch — 12 November 2026

The Coolify CSV for release ec5ab56 contains 463 findings across eight images
(186 distinct advisory IDs). Shared backend images repeat the same dependencies.

## Changes

- Upgrade Next.js and its ESLint configuration to 16.4.1 and sharp to 0.35.5.
  Apply compatible npm security fixes to the lockfile.
- Resolve patched Python dependencies in uv.lock and regenerate requirements.txt:
  certifi, cryptography, Django REST Framework, LangGraph/checkpoint/SDK, msgpack,
  PyJWT, pypdf, tornado, and urllib3.
- Use Python 3.13.18 and uv 0.13.7 for builds. Exclude uv and system pip from
  the application runtime, retaining installers in the test stage.
- Refresh OS packages during image builds. Require zlib >= 1.4-r0 in the
  Alpine gateway, frontend, and Redis images; retain the gateway libxslt fix.
- Remove npm, Corepack, and Yarn from the frontend runtime image.
- Keep PostgreSQL on major 17 with pgvector 0.8.7 and Bookworm. Refresh Debian
  packages and rebuild gosu 1.20 using Go 1.26.11 and x/sys 0.44.0.
- Build patched PostgreSQL/backup, Redis, and gateway images in Coolify.
  Existing volumes and database paths remain unchanged.
- Add CI image builds and PostgreSQL/vector, Redis, and Nginx smoke checks.
  Run backend CI with Python 3.13.

## Validation and remaining checks

Local production npm audit: zero findings. Eight moderate development-only
audit findings remain in the ESLint/typescript-eslint dependency chain. Its
current upstream release uses the affected minimatch version; do not force
npm's suggested downgrade of the Next.js ESLint configuration to version 15.

Backend: 1,046 tests passed and 10 skipped in the full local run. The remaining
test failed because of sandbox temporary-directory permissions, then passed
when rerun outside that restriction. Ruff and frontend lint/type checks passed.
The backend lockfile and Docker Compose configuration validate.

Image builds and service smoke tests must pass in CI. Local Docker image builds
were unavailable and the workstation had insufficient disk space for a full
production build. Local Python tests ran on 3.12; CI checks 3.13.

After deploying this commit, export a fresh Coolify scan. This patch is not a
claim of zero container vulnerabilities. Check any remaining Python binary or
Rust findings against their exact file paths and the upstream advisory's
affected-version ranges. Some scanner fixed-version fields refer to a different
Python release branch or a prerelease; do not upgrade to Python 3.16 solely to
match that field. Retain scan blocking and verify distribution backports.
