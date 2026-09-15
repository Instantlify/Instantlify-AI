# Delivery gates

Phases follow the supplied order. Passing tests with a fake provider is necessary but does not satisfy a phase's real-provider exit criterion.

| Phase | Scope | Exit evidence |
| --- | --- | --- |
| 0 — Foundation | Identity, tenancy, services, encryption, adapters, CI, frontend | Compose stack healthy; signup → workspace → logout/login persists; PostgreSQL/pgvector and isolation tests pass |
| 1 — Instagram | Live OAuth, long-lived exchange, proactive refresh, signed/deduplicated webhooks, outbound backoff | A real Business/Creator account connects, a real DM is stored, and a reply is actually delivered; Meta review tracked |
| 2 — Automation | Workspace graphs, persistent resumable execution, trigger matching, React Flow UI, contact cooldown | A nontechnical user publishes a real comment-keyword-to-DM flow; replay/loop/cooldown tests pass |
| 3 — AI sales agent | BYO encrypted LLM keys, ingestion/pgvector RAG, LangGraph state machine, guarded tools, voice, usage metering | Real grounded multistep conversation books a real calendar call with an audited deterministic guard |
| 4 — CRM/inbox | Unified leads/identities, live inbox, assignment/notes, segmentation, pluggable integrations | Three users collaborate across Instagram and WhatsApp and receive a real Slack hot-lead notification |
| 5 — Channels/billing/operations | WhatsApp/Telegram, Stripe tiers+meters, failure/limits policies, observability, load, export/delete | Paying tenants across three channels; billing reconciliation; failure drills and policy review evidence |

## Sequencing issue to resolve before Phase 4

The supplied Phase 4 exit requires WhatsApp, but the supplied Phase 5 introduces its adapter. Implement and validate the WhatsApp adapter at the end of Phase 4 to meet that exit, then complete Telegram and channel/billing hardening in Phase 5. This dependency should be confirmed when planning those increments. Do not pretend Phase 4 passes with Instagram alone.

## Production gates beyond source code

Business-owned Meta registration/review, public TLS/domain, actual privacy/legal information, provider sandbox/live credentials, calendar consent, Stripe product/pricing configuration, monitoring destinations and restore-tested infrastructure are external inputs. These should be tracked as evidence, not replaced by mocks or claims of deployment.
