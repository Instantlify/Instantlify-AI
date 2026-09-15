# Architectural decisions

## 2026-09-14 — Phase 0 scope

Ship account → workspace → authenticated dashboard as the foundation. Do not imply live provider availability before its exit test has been met. The local channel connection is visibly marked as a test; live paths fail closed. The pure automation kernel is a safety contract, not the Phase 2 execution engine. CRM, billing and agent models will be created with the requirements of their respective phases.

## Tenant boundaries

Shared PostgreSQL schema with a required workspace FK on every tenant-owned model. `Workspace` is the root tenant, and global users/auth session/JWT-blacklist records are infrastructure identity, so they do not have workspace FKs. Membership, audit, outbox, OAuth state and channel connection rows do.

`TenantModel.objects` fails closed for unqualified reads. Services must use `objects.for_workspace(workspace)` and supply the FK on creates. Requests resolve membership from the authenticated user and workspace path parameter, never a body-supplied tenant. UUIDs reduce accidental exposure but are not authorization. Unknown and inaccessible workspaces both return 404. Roles are checked separately.

`all_objects` is a deliberately visible escape hatch for membership-independent operational fan-out and OAuth state lookup. It is not used by tenant CRUD endpoints. This is application-level isolation, not PostgreSQL row-level security. New endpoints require cross-tenant tests; adding RLS would need a separately designed per-transaction context compatible with connection pooling and Celery. Cross-tenant foreign keys in future domain models must be validated at both the service and database boundary.

## Identity and browser security

Use Django session cookies for the first-party browser, with a same-origin Next.js proxy and CSRF checks for **all** mutations, including anonymous signup/login. Never expose a browser auth token to localStorage. DRF JWT endpoints serve non-browser clients, with five-minute access tokens, daily refresh tokens, rotation, and blacklist on refresh/revoke. Case-insensitive email uniqueness is enforced by PostgreSQL, not only validation. Password validation is shared with Django.

Owner is unique per workspace. An owner cannot be demoted via generic membership PATCH; an ownership transfer needs a dedicated atomic workflow. Owner/admin manage workspace settings; only owner changes roles; agents cannot connect channels or read audit events. Invitations and password-reset/email delivery are future work, and no nonfunctional UI action is shown for them.

## Durable async boundary

Creating a workspace, its owner membership, its audit event, and its outbox event is one transaction. Beat dispatches pending IDs, and a task locks the outbox row and commits its effect and completion together. Repeated delivery is safe. This avoids the commit-to-publish loss window of relying solely on `transaction.on_commit`. Queue acknowledgments are late; tasks must remain idempotent. Outbox processing in this phase has only local database effects. Future outbound provider effects require separate attempt records and handling of ambiguous timeouts; a transaction alone cannot guarantee exactly-once network delivery.

Celery uses JSON, bounded time limits and prefetch 1. Secrets and raw provider payloads will remain encrypted in PostgreSQL and be referenced by IDs, even when the user-facing integration requirement says to enqueue a raw payload. This satisfies the functional handoff while keeping queue inspection safe.

## Encryption and logs

Use `cryptography` Fernet authenticated encryption through a Django field, with an independent key ring. The first configured key encrypts; all configured keys decrypt. Encryption keys must be provisioned by the secret manager separately from DB backups. Never filter on encrypted fields. To rotate, deploy `[new, old]`, rewrite encrypted rows, verify, retain old keys for old backups, and only then retire them. Losing the key makes stored credentials unrecoverable.

API serializers enumerate safe fields. `Credentials.access_token` is excluded from dataclass repr. Logs use a closed JSON schema: timestamp, severity, module, event code and exception type. Free-form text, tracebacks, query strings, provider bodies and task arguments are not emitted by our formatter. This sacrifices some development convenience for a safe default; Phase 5 must add useful allowlisted correlation fields and sanitized error tracking.

## Channel abstraction and OAuth

`ChannelAdapter` defines send message, send voice note, parse webhook and refresh token without putting provider concepts in the automation kernel. Instagram is the first boundary; the fake is explicitly configured and forbidden by production settings. Live networking is not enabled in Phase 0. Its OAuth scaffolding uses cryptographically random state, stores only its SHA-256 digest, binds state to both user and workspace, expires it after ten minutes and consumes it under a row lock before exchange. Callback checks membership again. The later live exchange must validate the provider account and permissions and immediately acquire a long-lived token.

## Database and extension

PostgreSQL 17 with pgvector installed by the image and enabled by a migration. No second vector database. No embedding schema until document ingestion and model/provider dimensions are designed in Phase 3. The migration job runs once before web/worker startup. Local Compose's DB role can create the extension; managed deployments should provision the extension with a migration/admin role and use a less-privileged runtime role.

## Frontend and deployment

Next.js App Router, TypeScript, standalone container output. Browser → Next.js same-origin rewrite → Django. API responses are private/no-store. No client-side business-state mock data. The container build embeds `BACKEND_INTERNAL_URL`; moving the backend requires rebuilding the frontend. Local services bind to loopback, and PostgreSQL/Redis have no host ports. Full HTTPS ingress and edge throttling belong to the actual production deployment, not the local Compose defaults.

## Verification

Safety contracts for signatures and state transitions were written first. Unit/API tests require no live keys. PostgreSQL tests exercise pgvector and constraints; the Compose browser job tests actual HTTP cookies, CSRF, redirects and persistence. Frontend lint/type checks and build are separate gates. CI definitions become active when this source is pushed to a GitHub repository; defining a workflow does not prove a remote CI run has occurred.

## 2026-09-15 — Reliability, inbound pipeline and team invitations

**Migrations are part of the contract.** `apps.billing` shipped without a migrations package, so `migrate` never created its tables (pytest creates tables for unmigrated apps, and `makemigrations --check` ignores them). A test now fails if any `apps.*` app with models lacks migrations.

**Outbound rate limits are per connected account.** A single app-wide Meta counter let one tenant's spike starve every other tenant (50 workspaces shared 200 calls/hour). Each connection now has its own hourly bucket (`CHANNEL_CALLS_PER_HOUR`); `META_APP_CALLS_PER_HOUR` optionally adds an app-wide ceiling. The Lua script checks every bucket before consuming any, so a denial never burns budget elsewhere, and a limited delivery is rescheduled to the window reset without spending a send attempt. Verify the real limits for the approved Meta products before production and tune these values.

**Failures are terminal or backed off, never hot loops.** Webhook events retry with exponential backoff and become `failed` after six attempts (counted by the backlog check as lost messages). Stripe meter reporting backs off per record and only covers usage inside a paid subscription period. Malformed billing events and failed data operations are marked `failed`. Beat dispatchers use `enqueue_once` (a Redis `SET NX` marker with a TTL) so a backlog is not re-queued every second; tasks remain idempotent and a lost message is resent when the marker expires.

**Voice notes and segmentation are durable DB-polled jobs.** An inbound voice note is stored with `transcription_status=pending` and is not routed until a worker transcribes it; the transcript then goes through the same opt-out/segmentation/routing path as typed text. Network work never runs inside the webhook-processing transaction. Lead segmentation is debounced through `Lead.segment_due_at` (60 s after a message), claimed atomically, and a Slack notification is created only when a lead transitions to hot. Usage records now carry a `kind`: only `generation` counts toward the plan cap and the Stripe meter; `transcription` and `segmentation` are logged with token counts but not billed as AI messages.

**Rejected tool intents are audited and still answered.** A tool call the guard refuses (not allowed, invalid arguments, unconnected integration) is recorded as a `rejected`/`failed` ToolCall and the lead receives an honest fallback reply instead of silence. The deterministic guards themselves are unchanged.

**Invitations without email delivery.** Owners invite admins or agents; admins invite agents. A token is random, stored only as a SHA-256 digest, bound to the invited email, single-use and valid for seven days. Because no email provider exists yet, the accept link is returned once to the inviter to share out of band. Pending invitations hold a seat; the seat limit is enforced on creation and re-checked on acceptance. Locks are taken workspace-first in both paths. Removing a member returns their assigned conversations to the shared queue. The free plan has one seat, so teams require a paid plan (or an operator-set `seat_limit` locally).
