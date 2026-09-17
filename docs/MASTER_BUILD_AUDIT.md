# Master build audit — 2026-09-15

Compared the attached master brief with the current source, routes, workers, frontend pages and automated tests. This is a code-completeness assessment, not certification of production readiness. No application code was changed during this audit.

## Verification performed now

- Backend pytest: **157 passed, 4 skipped**. The local run did not exercise PostgreSQL vector/locking checks or the unavailable Redis-dependent check.
- Backend Ruff: passed.
- Django migration consistency: no changes detected.
- Frontend TypeScript and ESLint: passed.
- Did not rerun a production build, browser E2E suite, full Compose stack or real-provider acceptance in this audit. Browser tests now cover more than onboarding, but test source is not evidence of a fresh passing run.
- `VERIFICATION.md` records the older Phase 0 validation. The opening unchecked list in `IMPLEMENTATION_STATUS.md` is stale relative to the later increments and source code.

## Requirement mapping

| Phase | Present in source | Remaining before its exit criteria can be declared met |
| --- | --- | --- |
| 0 — Foundations | Django/DRF app structure, tenant managers and roles, session/JWT auth, encrypted credentials, Celery/Redis/beat/Flower, pgvector migration, Next.js, environment split and CI workflow | Fresh full-stack regression for the expanded application; remote CI execution and deployment evidence. Tenant relationship validation is at `save()` level and can be bypassed by bulk/queryset writes. |
| 1 — Instagram | OAuth exchange, encrypted long-lived token storage, scheduled refresh, HMAC webhook verification, durable dedupe/queue, outbound adapter, backoff and ambiguous-send handling | Real-account connect/receive/reply acceptance; Meta setup/review/permissions. Tighten queued-send policy checks described below. |
| 2 — Automation | Persisted automation/trigger/node/edge/state models, graph validation, keyword matching, wait/resume, delay/condition/button nodes, published snapshots, contact cooldown, React Flow editor and publish UI | Fresh browser verification and real Instagram comment-to-button delivery; broader concurrency and load validation. |
| 3 — AI agents | BYO OpenAI key/model configuration, document upload/chunk/embed/pgvector retrieval, explicit sales stages, guarded tools and booking confirmation, multi-round tool loop, voice transcription/ElevenLabs, usage records and audit UI | Real RAG/voice/calendar acceptance; accurate embedding/transcription costs and per-call accounting; separate simple single-turn reply path. Only OpenAI plus the fake provider is implemented. |
| 4 — CRM/inbox | Lead/channel identities, merge API, realtime inbox with polling fallback, assignment, notes, role restrictions, segmentation and hot-lead Slack jobs; Calendar/Cal.com/Airtable/Notion/GHL/Slack adapters; hosted Google/Slack OAuth with disconnect and reconnect flags (2026-09-16) | Real multi-channel team acceptance and live integration validation. |
| 4.5 — Parity | ScheduledPost and publisher, calendar screen, branded public bio page/click tracking, workflow JSON export/import, Attio adapter | Real content publishing acceptance, including durable media-container readiness handling for video; public hosting acceptance for bio pages. |
| 5 — Channels/billing/scale | WhatsApp, Telegram and Messenger adapters; platform Stripe subscriptions, tier limits, meter jobs and failure states; structured logs, Sentry setup, health/backlog checks; export/delete/retention jobs | Billing reconciliation hardening, realistic 50-workspace load test, external webhook uptime/page routing, full data lifecycle coverage, production deployment and policy review. |
| 6 — Differentiators | Funnel/revenue analytics, deterministic A/B assignment and promotion, in-chat Stripe Checkout links, sentiment/urgency handoff, free marketplace publishing/install, agency branding/client workspaces, public API and signed REST hooks, Messenger | Paid marketplace commerce/payouts; packaged/published Zapier/n8n/Make connectors; custom-domain ownership/TLS provisioning; triage ahead of deterministic automation routing; live proof and marketing for 2–3 differentiators. |

## Concrete unfinished or partial implementation

1. **Paid marketplace:** *Resolved 2026-09-16.* Stripe Connect payouts and destination-charge checkouts are implemented and tested with a mocked Stripe client; live sandbox acceptance is still pending.
2. **Connectors:** *Partly resolved 2026-09-16.* Zapier app, n8n node and Make app packages exist under `connectors/` (Zapier tested and n8n built locally; none published to a directory yet).
3. **Messaging safety at dispatch:** *Resolved 2026-09-16* (send-time re-check of opt-out, window and one-private-reply-per-comment; tests in `test_phase_hardening.py`). Original finding: `apps/crm/services.py` sets the inbound time to processing time and checks opt-out/window eligibility when queuing. `apps/channels/tasks.py` checks connection status/expiry before sending, but does not recheck the lead's current opt-out or conversation window. A delayed event or queued message can therefore outlive the conditions that allowed it. Private-comment reply limits also need explicit enforcement.
4. **Billing reconciliation:** *Resolved 2026-09-16* (invoice/subscription matching, unmapped-price flagging, sync-time reconciliation, metering limited to open subscriptions). Original finding: `apps/billing/tasks.py:apply_event` allows `invoice.paid` to set an account active whenever a subscription ID exists, without matching the invoice to the current subscription or guarding canceled status. Unknown price mappings retain previous limits. Add targeted reconciliation tests and handling.
5. **AI accounting:** `agents/runtime.py` aggregates calls within a turn into one usage record; it does not provide a separate usage record for every call. RAG records embedding tokens but leaves cost at its default. Transcription marks a record complete without measured usage/cost. This falls short of the brief's every-call token/cost accounting.
6. **Simple replies:** *Resolved 2026-09-16.* `AgentConfig.mode=simple` routes runs to `agents/simple.py`: one grounded model call, no tools, no triage call, checkpointed and metered like an agent turn.
7. **Triage coverage:** Sentiment/urgency classification is inside the AI runtime. `automations/services.py:route_message` can resume or start a deterministic flow before an agent run is created. Thus triage does not inspect every inbound message before automation continues.
8. **Data lifecycle:** *Resolved 2026-09-16 for local data* (export coverage enforced by test, manifest of external systems, explicit retention policy). External providers and backups remain outside local deletion. Original finding: Export covers the original CRM, automation, knowledge, usage and audit tables, but omits newer content, bio, analytics, payments and marketplace data. Retention scrubs selected payload tables; newer customer-bearing payload stores need an explicit retention policy. Deletion of local workspace records is not proof of deletion in external providers or backups.
9. **Tenant defense:** `TenantModel.save()` validates tenant-related FKs, and API queries are scoped. There are no comprehensive database-level composite tenant FK constraints; bulk writes can bypass the save guard. This is a hardening gap, not evidence that a tested API endpoint leaks data.
10. **White label:** Branding inheritance and custom-host lookup exist. Domain ownership verification, automated certificates and reseller billing/payout management are not implemented as a complete service.
11. **Operational readiness:** Health/backlog checks and Sentry integration exist. No realistic 50-workspace traffic benchmark or configured external webhook uptime paging was found. Next rewrites only API/health; production routing still needs WebSockets, provider webhooks and signed voice media paths directed to Django.
12. **Content publishing:** *Resolved 2026-09-17.* The container ID is persisted before any publish call, status is polled with backoff until `FINISHED`, `ERROR`/`EXPIRED` fail without publishing, an ambiguous publish is resolved by the container reporting `PUBLISHED`, and lost workers resume instead of re-creating. Real video acceptance still needs a live account.

## External acceptance still unproven

- Meta app registration, advanced access review, real Instagram/WhatsApp/Messenger traffic and permissions.
- Real Telegram delivery and public webhook registration.
- Real provider LLM/RAG/ElevenLabs output and Google Calendar/Cal.com bookings.
- Real subscription invoices, metered charges and tenant checkout payments.
- Public HTTPS deployment, domain routing, monitoring alerts, policy/compliance review and production backup/restore.

**Conclusion:** This is a substantial implementation with backend code and UI across all requested phases, not merely Phase 0. It is not fully implemented or production-ready. Finish the concrete gaps and rerun full-stack acceptance before marking the phase exit criteria complete.
