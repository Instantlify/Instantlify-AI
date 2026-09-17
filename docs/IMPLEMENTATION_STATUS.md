# Remaining implementation

The request now includes all phases. Work proceeds in order, with automated tests at each increment. Live provider acceptance remains separately tracked and requires configured accounts and credentials.

- [ ] Phase 1: live Instagram adapter/OAuth, refresh, signed durable webhook ingress, delivery queue
- [ ] Phase 2: resumable automation graphs, trigger matching, cooldowns, visual editor
- [ ] Phase 3: agent configuration, document/RAG pipeline, guarded LangGraph tools, voice, metering
- [ ] Phase 4: CRM, unified realtime inbox, team assignment/notes, integration adapters
- [ ] Phase 5: WhatsApp/Telegram, Stripe subscriptions/meters, limits, observability, retention/export/deletion
- [ ] Full regression, migration, browser and container verification

External acceptance: real Instagram/WhatsApp/Telegram delivery, Meta review, calendar booking, paid Stripe billing and public production deployment are not established by local/fake-provider tests.

## 2026-09-15 hardening increment

- [x] Billing tables were never migrated; migrations added plus a regression test for unmigrated apps
- [x] Per-account outbound rate limits (optional app ceiling); rate-limited sends wait for the window reset
- [x] Backoff/terminal states for poison webhooks, Stripe meter reporting, billing events and data operations; dispatchers no longer re-queue in-flight jobs
- [x] Voice notes transcribed by a durable job and routed like text; AI lead segmentation scheduled on inbound messages; Slack ping only on transition to hot
- [x] Team invitations (seat-limited, email-bound, single-use) and member removal, with Team tab UI
- [x] Tests for the live automation executor (`automations.tasks.step`) and the agent tool guards


## 2026-09-15 parity and differentiator increment (backend)

- [x] Funnel analytics (`FunnelEvent`, distinct-lead funnel, per-automation/channel, revenue)
- [x] A/B experiments with deterministic per-lead assignment, per-arm results, manual and automatic winner promotion
- [x] Automation export/import; community marketplace (publish, list, install; paid installs gated until a payout rail exists)
- [x] Agent: triage (keyword + LLM sentiment/urgency) → human handoff, explicit sales stage machine, bounded multi-round tool loop with results fed back, stuck-call guard, checkpointed rounds
- [x] In-chat payments on the tenant's own Stripe (offers, guarded `create_payment_link`, per-workspace signed webhook, paid → won + revenue)
- [x] Content calendar (Instagram publish) and link-in-bio pages with click tracking
- [x] Public API keys (hashed, scoped, throttled), `/api/v1/`, REST-hook subscriptions, signed outbound webhooks with backoff and SSRF guard
- [x] White-label: agency → client workspaces, branding with custom domain resolution
- [x] Messenger channel, per-provider Meta secrets, OAuth channel-limit check, Attio integration, Sentry with scrubbing


## 2026-09-15 frontend increment

- [x] Route-based app shell (`/w/<workspace>/…`), workspace context, white-label branding applied to the shell and sign-in
- [x] Overview, Team (invites, removal), Activity, Settings (name, branding, agency clients, export/delete), Help
- [x] Inbox with WebSocket live hints + polling fallback, assignment, status/handoff, AI toggle, notes, lead stage/tags/fields, payment links
- [x] Automations list and React Flow builder (palette, triggers, node config, start node, save/publish)
- [x] AI agent (settings, tools, triage, knowledge base upload, audit), Analytics (funnel, per automation/channel, experiments)
- [x] Content calendar, Link in bio editor + public page, Templates (marketplace, publish, import/export)
- [x] Payments (offers, checkouts, platform plans/usage), Integrations (providers, channels, simulate, API keys, webhooks)
- [x] Public pages: `/p/<slug>/`, checkout return pages

Still open (external): live Instagram/WhatsApp/Messenger/Telegram delivery, Meta review, real calendar bookings and Stripe payments, production deployment.

## 2026-09-16 — Paid marketplace and connectors

- [x] Stripe Connect payouts for template authors (Accounts v2 recipient, express dashboard, hosted onboarding, capability re-checks, dashboard login link)
- [x] Paid template installs via platform Checkout destination charges, platform fee, webhook and re-read fulfilment, idempotent purchases, purchase history UI, `marketplace` kill switch
- [x] Zapier app (`connectors/zapier`, 10 tests passing) and n8n community node (`connectors/n8n`, builds) over `/api/v1/`; `GET /api/v1/me/`; lead `email` filter
- [x] Make custom app package (`connectors/make`, JSON definitions; no signature verification possible on Make)
- [x] Connectors panel on the Integrations page, `connectors/README.md`, `docs/PUBLIC_API.md` connector section
- [ ] Publishing the Zapier/n8n packages to their directories; live Stripe Connect acceptance in a sandbox

## 2026-09-16 — Phase 1, 4 and 5 code gaps (from the master audit)

- [x] Phase 1: one private reply per comment (queue-time fallback to the DM thread, send-time `private_reply_limit`); opt-out and messaging window re-checked when a queued delivery is actually sent
- [x] Phase 4: hosted OAuth for Google Calendar and Slack (user-bound single-use state, encrypted tokens, refresh-token preservation, Slack channel picked at install), disconnect with best-effort remote revocation, `status` on integrations with `reconnect_required` set by failed refreshes
- [x] Phase 5 billing: invoice events only apply to the tracked open subscription, deletion of a replaced subscription is ignored, unmapped prices are flagged (`billing.price_unmapped`) without cutting limits, metering stops for closed subscriptions, the subscription sync reconciles drift against Stripe (`billing.reconciled`)
- [x] Phase 5 data lifecycle: export covers every customer-bearing tenant table (test enforces coverage) plus a manifest of external systems; retention has an explicit per-store policy that skips in-flight work
- [x] Phase 5 load: `manage.py loadtest --workspaces 50 --messages 20` drives the durable pipeline across workspaces and reports per-stage throughput and p50/p95
- [x] Integrations page: connect/reconnect/disconnect buttons and hosted sign-in return handling
- [x] Instagram publishing: container ID persisted, processing polled with backoff, publish only when `FINISHED`, ambiguous publishes resolved via container status, expired containers failed
- [x] Simple single-turn reply mode beside the LangGraph agent (`AgentConfig.mode`, `agents/simple.py`): one grounded call, no tools, checkpointed reply, keyword handoff kept; selectable on the AI agent page
- [ ] External: real Instagram private replies, real Google/Slack installs, Stripe sandbox billing reconciliation, a PostgreSQL load run on production-like hardware
