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

Still open: React Flow builder, unified inbox UI and WebSocket client, agent config/billing UI, multi-turn agent tool loop, Sentry initialization, live provider verification.
