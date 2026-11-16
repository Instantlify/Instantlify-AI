# Implementation status

**26 October 2026:** The sections below retain historical phase checkpoints. Current feature
scope and verification are in [PARITY_WORKLOG.md](PARITY_WORKLOG.md). Local signed Stripe
test callbacks now cover trial creation, update, plan change/restoration and cancellation;
other Stripe sandbox scenarios remain separate checks in
[LIVE_PROVIDER_VERIFICATION.md](LIVE_PROVIDER_VERIFICATION.md).

Legend: ✅ done and covered by automated tests · ❌ remaining. "Done" means the code exists
and passes the local suites (backend pytest: 386 passed, 9 skipped on 2026-09-18; Playwright: 8 of 8 before the
gap-closing increment, not re-run since)
against the Compose stack with fake providers. It does not mean accepted against a live
provider; those items are listed separately under *Remaining*.

## Phases (code)

- ✅ Phase 1: Instagram adapter/OAuth, token refresh, signed durable webhook ingress, delivery queue
- ✅ Phase 2: resumable automation graphs, trigger matching, cooldowns, visual editor
- ✅ Phase 3: agent configuration, document/RAG pipeline, guarded LangGraph tools, voice, metering
- ✅ Phase 4: CRM, unified realtime inbox, team assignment/notes, integration adapters
- ✅ Phase 5: WhatsApp/Telegram/Messenger, Stripe subscriptions/meters, limits, observability, retention/export/deletion
- ✅ Phase 6: analytics, A/B experiments, in-chat payments, marketplace, white-label, public API, connectors
- ✅ Platform console (2.5.1–2.5.15): all 21 tabs read live data; no hardcoded figures remain
- ✅ Full local regression, migrations, browser and container verification (2026-09-18)
- ✅ Gap-closing increment (`implementation_plan.md` phases 1–8 complete): see the last section

## Remaining

Code gaps (from `MASTER_BUILD_AUDIT.md`; closed items are in the last section):

- ❌ Database tenant triggers verified on PostgreSQL: written and covered by tests that skip on
      SQLite; not yet run (local Docker was down, disk full). CI's PostgreSQL job runs them
- ❌ Rebuild the Compose stack and re-run Playwright after the gap-closing increment
- ❌ Publishing the Zapier/n8n/Make packages: the release pipeline exists; it needs
      `NPM_TOKEN`, `ZAPIER_DEPLOY_KEY`, a one-time `zapier register`, and each directory's review

External acceptance (cannot be established by local/fake-provider tests):

- ❌ Meta app registration and App Review; real Instagram/WhatsApp/Messenger traffic
- ❌ Real Telegram delivery and public webhook registration
- ❌ Real LLM/RAG/ElevenLabs output; real Google Calendar/Cal.com bookings; real Google/Slack installs
- ❌ Stripe sandbox acceptance: subscriptions, metered charges, Connect payouts, tenant checkouts,
      promo coupons, billing reconciliation (the console's Subscriptions vs Churn and MRR Growth
      charts stay empty until Stripe events and nightly snapshots exist)
- ❌ PostgreSQL load run on production-like hardware
- ❌ Public HTTPS deployment, domain routing, monitoring alerts, backup/restore, policy review

Deploy notes: everyone is signed out once after the next deploy (the ban-aware login backend
replaces the old one); production refuses to start without SMTP settings.

## 2026-09-15 hardening increment

- ✅ Billing tables were never migrated; migrations added plus a regression test for unmigrated apps
- ✅ Per-account outbound rate limits (optional app ceiling); rate-limited sends wait for the window reset
- ✅ Backoff/terminal states for poison webhooks, Stripe meter reporting, billing events and data operations; dispatchers no longer re-queue in-flight jobs
- ✅ Voice notes transcribed by a durable job and routed like text; AI lead segmentation scheduled on inbound messages; Slack ping only on transition to hot
- ✅ Team invitations (seat-limited, email-bound, single-use) and member removal, with Team tab UI
- ✅ Tests for the live automation executor (`automations.tasks.step`) and the agent tool guards


## 2026-09-15 parity and differentiator increment (backend)

- ✅ Funnel analytics (`FunnelEvent`, distinct-lead funnel, per-automation/channel, revenue)
- ✅ A/B experiments with deterministic per-lead assignment, per-arm results, manual and automatic winner promotion
- ✅ Automation export/import; community marketplace (publish, list, install; paid installs gated until a payout rail exists)
- ✅ Agent: triage (keyword + LLM sentiment/urgency) → human handoff, explicit sales stage machine, bounded multi-round tool loop with results fed back, stuck-call guard, checkpointed rounds
- ✅ In-chat payments on the tenant's own Stripe (offers, guarded `create_payment_link`, per-workspace signed webhook, paid → won + revenue)
- ✅ Content calendar (Instagram publish) and link-in-bio pages with click tracking
- ✅ Public API keys (hashed, scoped, throttled), `/api/v1/`, REST-hook subscriptions, signed outbound webhooks with backoff and SSRF guard
- ✅ White-label: agency → client workspaces, branding with custom domain resolution
- ✅ Messenger channel, per-provider Meta secrets, OAuth channel-limit check, Attio integration, Sentry with scrubbing


## 2026-09-15 frontend increment

- ✅ Route-based app shell (`/w/<workspace>/…`), workspace context, white-label branding applied to the shell and sign-in
- ✅ Overview, Team (invites, removal), Activity, Settings (name, branding, agency clients, export/delete), Help
- ✅ Inbox with WebSocket live hints + polling fallback, assignment, status/handoff, AI toggle, notes, lead stage/tags/fields, payment links
- ✅ Automations list and React Flow builder (palette, triggers, node config, start node, save/publish)
- ✅ AI agent (settings, tools, triage, knowledge base upload, audit), Analytics (funnel, per automation/channel, experiments)
- ✅ Content calendar, Link in bio editor + public page, Templates (marketplace, publish, import/export)
- ✅ Payments (offers, checkouts, platform plans/usage), Integrations (providers, channels, simulate, API keys, webhooks)
- ✅ Public pages: `/p/<slug>/`, checkout return pages


## 2026-09-16 — Paid marketplace and connectors

- ✅ Stripe Connect payouts for template authors (Accounts v2 recipient, express dashboard, hosted onboarding, capability re-checks, dashboard login link)
- ✅ Paid template installs via platform Checkout destination charges, platform fee, webhook and re-read fulfilment, idempotent purchases, purchase history UI, `marketplace` kill switch
- ✅ Zapier app (`connectors/zapier`, 10 tests passing) and n8n community node (`connectors/n8n`, builds) over `/api/v1/`; `GET /api/v1/me/`; lead `email` filter
- ✅ Make custom app package (`connectors/make`, JSON definitions; no signature verification possible on Make)
- ✅ Connectors panel on the Integrations page, `connectors/README.md`, `docs/PUBLIC_API.md` connector section
- ❌ Publishing the Zapier/n8n packages to their directories; live Stripe Connect acceptance in a sandbox

## 2026-09-16 — Phase 1, 4 and 5 code gaps (from the master audit)

- ✅ Phase 1: one private reply per comment (queue-time fallback to the DM thread, send-time `private_reply_limit`); opt-out and messaging window re-checked when a queued delivery is actually sent
- ✅ Phase 4: hosted OAuth for Google Calendar and Slack (user-bound single-use state, encrypted tokens, refresh-token preservation, Slack channel picked at install), disconnect with best-effort remote revocation, `status` on integrations with `reconnect_required` set by failed refreshes
- ✅ Phase 5 billing: invoice events only apply to the tracked open subscription, deletion of a replaced subscription is ignored, unmapped prices are flagged (`billing.price_unmapped`) without cutting limits, metering stops for closed subscriptions, the subscription sync reconciles drift against Stripe (`billing.reconciled`)
- ✅ Phase 5 data lifecycle: export covers every customer-bearing tenant table (test enforces coverage) plus a manifest of external systems; retention has an explicit per-store policy that skips in-flight work
- ✅ Phase 5 load: `manage.py loadtest --workspaces 50 --messages 20` drives the durable pipeline across workspaces and reports per-stage throughput and p50/p95
- ✅ Integrations page: connect/reconnect/disconnect buttons and hosted sign-in return handling
- ✅ Plan model (2.6): `Plan`/`PlanPrice`/`PlanLimits`, seeded tiers with monthly and annual prices, `BillingAccount` on a `PlanPrice`, limits derived from the plan; one gate (`billing.gating`) with 402 `upgrade_required`; seats and channel connects go through it, including before Meta OAuth starts
- ✅ Prepaid AI credits (2.10): `ModelPricingRate` rate card with wildcard matching and fallback, `AICreditBalance` with auto top-up, `AICreditTransaction` ledger (charged, real cost, balance snapshot) per model call and embedding batch; explicit `billing_mode` per workspace; `needs_payment` parking with notification; top-up checkout that saves the card; tenant Credits panel on Payments. Console AI Credits page is 2.5.4 (next)
- ✅ Plan gating (2.6): every named gate point (agent config and runs, integrations connect and jobs, scheduled posts and publishing, voice tool, seats, channel connect before OAuth); downgrade soft-lock on connections beyond the cap; 7-day trial on first checkout; `GET /api/public/plans/`; shared pricing cards on the public `/pricing` page, the Payments page and the in-app upgrade modal opened by any 402; console Tiers tab (2.5.7) with monthly/yearly toggle, read-only defaults and editable custom tiers
- ✅ Instagram publishing: container ID persisted, processing polled with backoff, publish only when `FINISHED`, ambiguous publishes resolved via container status, expired containers failed
- ✅ Simple single-turn reply mode beside the LangGraph agent (`AgentConfig.mode`, `agents/simple.py`): one grounded call, no tools, checkpointed reply, keyword handoff kept; selectable on the AI agent page
- ❌ External: real Instagram private replies, real Google/Slack installs, Stripe sandbox billing reconciliation, a PostgreSQL load run on production-like hardware

## 2026-09-18 growth increment — the console's data layer, and the wizard that fills it

Six console sections were rendering shaped fixtures because nothing backed them. They
now read their own tables, and the tenant-facing surfaces that produce those rows exist.

- ✅ Signup funnel (2.5.2): `SignupFunnelEvent`, and the five-step wizard at `/onboarding`
      (`connect-instagram → workspace → team → integrations → payment`) built from the same
      step list the backend validates against, so the two cannot drift. Progress resumes
      server-side; unknown steps are rejected rather than silently recorded; a teammate's
      tour activity is attributed to the real account (`is_owner=False`), never counted as
      a separate signup. Funnels count distinct users, and the worst drop-off is named.
- ✅ Website stats (2.5.3): first-party `PageVisit` / `PageSignup` with first-touch vs
      last-touch attribution, an anonymous write-only `/api/growth/visit/`, and signup
      attribution wired into `SignupView` in a way that cannot fail a signup.
- ✅ Segments (2.5.6): `SegmentCategory` (editable, read by the classifier without a
      redeploy) and `UserSegment`, derived from a connected account's public profile.
      `ChannelConnection.profile` now carries bio/website/followers; classification re-runs
      on every reconnect and deletes the previous verdict first, so a rebranded account
      cannot keep a stale category. Thin evidence produces no row rather than a guess.
- ✅ Blog (2.5.9): `BlogPost` / `BlogCategory` / `BlogPostView` with console CRUD, a public
      read API, and a beacon that records the deepest scroll and longest dwell per session.
- ✅ Customer support (2.5.10): `SupportTicket` with inline assignee/resolution in the list,
      fed by both the in-app form and the platform agent's `create_ticket`.
- ✅ AI agent config (2.5.11): `PlatformKnowledgeDocument` / `PlatformKnowledgeSection` and
      Instantlify's own support agent — separate tables, separate retrieval, separate key from the
      tenant agent. Sentinel tokens (`[[REQUEST_NAME_CARD]]`, `[[REQUEST_EMAIL_CARD]]`) with
      the ticket gate enforced in code, not only in the prompt. Editing a section clears its
      embedding; re-embedding is an explicit operator action, never per keystroke.
- ✅ Billing audit (2.5.12): `BillingAuditRun` plus an on-demand `scan_billing` Celery task
      comparing local subscription state against live Stripe (stale subs, cardless trials).
      Explicitly never scheduled — it spends real API calls.
- ✅ Promo offers (2.5.13): `PromoCampaign` / `PromoCampaignEvent`, all live config, with
      shown / claimed / redeemed kept as three separate numbers.
- ✅ Notifications (2.5.14): `Announcement` / `AnnouncementView` — popups once per viewer,
      strips persistent, targeted by page and by tier independently.
- ✅ Email templates (2.5.15): `EmailTemplate` plus `send_transactional_email(name, to, context)`
      as the single send path, seeded with twelve templates in a data migration. A `draft`
      row is editable but refuses to send. Welcome and ticket acknowledgement now go through it.
- ✅ Console: every growth tab reads live data, with write endpoints for blog, tickets,
      knowledge, promos, announcements, templates, segment categories and the billing scan —
      each `@protected`, POST-only and audited.

- ❌ External: Meta App Review, real Instagram/WhatsApp/Telegram delivery, real Google/Slack
      installs, Stripe sandbox reconciliation, a PostgreSQL load run on production-like hardware


## 2026-09-18 console completion increment

- ✅ Dashboard (2.5.1): `PlatformMetricsService`; every card computed from data, cached
      figures labelled with their time, Stripe/Database source and 7/30/90/365-day windows.
      No figure without a source (Claude MCP) shows a number.
- ✅ Users (2.5.5): leaderboard, search and filters, per-user cards; Ban cascades through
      sign-in, open sessions, bearer tokens, refresh tokens and every owned workspace's kill
      switch, and Unban lifts only the pauses the ban created; operator email via the
      configured webhook; fresh billing-portal link; history; create user
- ✅ AI Credits (2.5.4): per-key provider cards incl. named keys, owner-only throttled Test;
      editable rate card with protected fallback and a display-only units switch; ledger
      search, type filter and pagination
- ✅ Automations (2.5.8): `duplicate()` and `transfer()` services, `AutomationTransferLog`,
      per-automation run history
- ✅ Website Stats first-touch toggle; blog edit prefill (saving an edit no longer blanks
      the post), archive, categories, daily-views chart; notification editing
- ✅ Tenant app: announcement strips and popups, promo gift box, persistent connect prompt,
      in-app support assistant, first-party visit tracking, public `/blog` with scroll and
      dwell beacon, product-tour events
- ✅ Money and email loops: claimed campaigns become Stripe coupons at checkout and
      `redeemed` is recorded once per subscription; plan-change email from the live invoice
      preview; portal link created at send time; daily trial reminder; credits-low and
      auto-top-up-failed emails
- ✅ Config: SMTP settings (required in production), every setting documented in
      `.env.example`


## 2026-09-18 reliability and console-truth increment

- ✅ Dispatch latency: `enqueue_once` markers were never released, so a multi-node flow advanced
      one node per 30 s and an agent run deferred behind another waited 30 s. `step` and
      `process_run` now release the marker when their row is still legitimately due
- ✅ Agent reconciler no longer queues an AI reply for a message a flow, teammate or the agent
      already answered (leads were getting duplicate AI greetings when AI was switched on)
- ✅ `/api/auth/csrf/` exempt from the anonymous per-IP throttle; a busy signed-in user hit 429
      and could not save or sign out ("Unable to establish a secure session")
- ✅ CSRF token race on first load: concurrent first writes share one token fetch
- ✅ Dashboard charts computed from data (`platform_ops/charts.py`, `PlatformMetricsService.charts`):
      signups, subscriptions vs churn, plan donut, 12-month MRR; all follow the window selector
      and show an empty state instead of an invented series. The fixed mockup SVGs are gone
- ✅ Support nav badge shows the real unread count; fake "Last 30 Days ▾" dropdown pills removed
- ✅ `manage.py purge_e2e_accounts` (fake-adapter mode only) run by Playwright's global teardown,
      so browser runs stop filling the console with "E2E Studio" workspaces
- ✅ Browser suite: 8 of 8 passing (save-then-reload race and two ambiguous locators fixed)


## 2026-09-18 gap-closing increment (`implementation_plan.md`)

- ✅ Plan phase 2 — voice metering: Whisper's measured duration stored as
      `UsageRecord.audio_seconds`; `charge_transcription` debits credits per second from a
      seeded `whisper-1` rate (units are seconds; editable on the console rate card); BYO-key
      workspaces get the real cost recorded, never a debit
- ✅ Plan phase 3 — early triage: `crm/triage.py` checks every inbound message for escalation
      phrases before `route_message`; a hit calls `hand_off` (flows stopped, AI paused, team
      paged) and, if a bot was answering, sends the "bringing a team member" reply. Whole-word
      phrases only; the workspace's own handoff keywords and triage switch apply. The model's
      sentiment/urgency check stays in the agent run (no provider call in the ingest path)
- ✅ Plan phase 1 — providers: Anthropic (Messages), Gemini (generateContent, thought
      signatures round-tripped) and xAI (Chat Completions) adapters behind `provider_for`;
      optional fallback provider on 429/5xx, platform credits only, billed at the answering
      model's rate; embeddings always OpenAI (`embedder_for`, `embedding_api_key` for BYO
      non-OpenAI workspaces); agent page provider, fallback and embedding-key fields
- ✅ Plan phase 6 — MCP server: `/api/mcp/`, Streamable HTTP in stateless JSON mode as a Django
      view (the SDK's session manager needs an ASGI lifespan the Channels router lacks); API-key
      Bearer auth, six tools (`list_conversations`, `get_conversation_messages`,
      `get_lead_details`, `get_workspace_metrics`, `send_message`, `trigger_automation`) gated by
      read/write scope; `MCPClient` rows feed the console card; included in data export
- ✅ Plan phase 4 — tenant isolation below `save()`: `TenantQuerySet` validates `bulk_create` /
      `bulk_update`; `tenants/isolation.py` generates deferred PostgreSQL constraint triggers for
      every tenant FK (child and parent side) after each migrate. PostgreSQL run still pending
      (see *Remaining*)
- ✅ Plan phase 7 — operations: `deploy/Caddyfile` and `deploy/nginx.conf` (WebSockets, webhooks,
      streamed voice media, API, console host); `probe_uptime` every minute pages Slack and/or
      PagerDuty once per incident and resolves on recovery; settings documented
- ✅ Plan phase 8 — connectors: `connectors/scripts/publish.py` (tests, `zapier validate`, n8n
      build and `npm pack`, Make schema check and bundle) and `.github/workflows/connectors.yml`
      releasing on `connectors-vX.Y.Z`; Zapier publishing blocker (D021) fixed
- ✅ Plan phase 5 — white-label domains, automated TLS & reseller billing: `WorkspaceBranding` extended with
      `custom_domain_status`, `verification_token`, `verified_at`, and `tls_status`; domain ownership verification
      service (`apps.tenants.domain_verification`) supporting DNS TXT challenge (`_instantlify-challenge.<domain>`) and
      CNAME routing to platform domains with on-demand API trigger (`POST /api/workspaces/<id>/branding/verify-domain/`);
      edge On-Demand TLS validation endpoint (`GET /api/v1/tls/check-domain/`) queried by Caddy `on_demand_tls`;
      `DynamicAllowedHosts` container allowing verified tenant domains dynamically in Django `ALLOWED_HOSTS`;
      Caddyfile updated with On-Demand TLS edge proxying for verified tenant domains; agency consolidated reseller
      billing (`apps.billing.reseller`) rolling child workspace tier limits, subscription status, and prepaid AI credit
      balances up to the parent agency workspace (`BillingAccount` and `AICreditBalance`); 10 tests in
      `test_custom_domains_and_reseller.py`.
- ✅ Hassle-Free Zero-Tech Experience & Multi-Channel Expansion:
      - **Platform Voice Managed Fallback**: Inbound Whisper voice note transcription and ElevenLabs outbound voice notes
        (`apps/agents/voice.py`) now seamlessly fallback to platform-level keys (`PLATFORM_ELEVENLABS_API_KEY`) and default voices,
        allowing clients to use voice without signing up for ElevenLabs or managing developer API keys.
      - **LinkedIn Channel Integration**: Official OAuth 2.0 flow (`LinkedInOAuthStartView`, `LinkedInOAuthCallbackView`),
        adapter (`LinkedInAdapter`) and webhook ingestion (`/webhooks/linkedin/`) for LinkedIn Company Pages, handling inbound DMs and post comments.
      - **Snapchat Lead Ads & Bio Concierge Integration**: Ingress webhook endpoint (`/webhooks/snapchat/`) to capture and parse Snapchat
        Lead Gen Ad submissions, automatically creating/updating CRM leads and identities and triggering sales conversation flows.
      - **Client UI Streamlining**:
        - Frontend Integrations page now features **1-Click Connect** OAuth buttons for Meta (Instagram / Messenger) and LinkedIn.
        - Advanced developer webhook URLs and manual channel tokens are collapsed into tidy `<details>` accordions to eliminate tech jargon for non-tech clients.
        - Agent configuration page displays clear "Platform-Managed AI (Zero Setup)" pill when platform credits are active, hiding raw developer token cost inputs inside an advanced accordion.
      - Unit test suite: 5 tests in `backend/tests/test_linkedin_and_voice_platform.py` covering fallback voice synthesis, LinkedIn OAuth start/callback, LinkedIn webhooks, and Snapchat lead ads. Next.js and ESLint passing cleanly.

