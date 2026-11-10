# Nemio versus Boosend — source and validation audit

Historical baseline before the implementation changes in this session. For current changes and verification, see [the implementation status](BOOSEND_IMPLEMENTATION_STATUS_2026-11-10.md).

Audit date: 10 November 2026, Asia/Karachi.

## Verdict

Nemio is a substantial implementation with broad overlap, but it is not yet demonstrably a production replacement for Boosend or better overall. Several reference features have narrower equivalents or no equivalent. The current quality gates are not all green. Passing local tests does not establish live delivery, commercial reliability, UX parity or production readiness.

This audit inspected the local Boosend source at `C:/Users/Jawad/Desktop/Boosend` and Nemio's routes, models, runtime services, integration configuration, tests, CI and existing verification records. Boosend was treated as read-only. No production customer data, messages, automations or subscriptions were changed. The owner's statement that Boosend runs in production is context; this audit did not independently verify its deployed revision or every reference workflow.

## Fresh checks

| Check | Result on this checkout | Interpretation |
|---|---|---|
| Backend pytest, SQLite test settings | **806 passed, 1 failed, 9 skipped**, 65.37 seconds | Broad local behavior coverage; suite is not fully green. No fresh PostgreSQL/Redis integration acceptance. |
| Backend Ruff lint | Passed | Static check only. |
| Backend Ruff formatting | Failed: **18 files** require formatting; 325 already formatted | CI formatting gate would fail with this tool/environment. |
| Django system check | Passed, zero issues | Test settings only; not a production deployment check. |
| Migration drift | No changes detected | Model/migration consistency; does not prove deployment migrations are applied. |
| Frontend TypeScript | Passed | No detected type errors. |
| Frontend ESLint | Failed: **7 errors, 70 warnings** | Errors are in Settings; strict zero-warning CI also rejects warnings elsewhere. |
| Frontend production build | Failed fetching DM Sans and Manrope from Google Fonts | Environment/build dependency failure, not proof of a TypeScript or application logic defect. A successful current production artifact was not produced. |
| Playwright suite, default Chromium | **6 browser-independent guided compiler tests passed, 127 failed, 8 skipped**; browser executable missing | Compiler cases verified. Browser-dependent failures are launch/environment failures, not evidence of 127 application bugs. |
| Browser suite, installed Chrome | Stopped after 3 navigation failures; 138 skipped/not completed in runner output | Sandbox run reported network access denied; outside-sandbox retry reported connection timeout to local dev server. These are infrastructure failures, not 3 established product bugs. Zero successful browser checks in this audit. |
| Docker/Compose | Linux engine pipe absent; start command did not make engine available | No fresh full-stack readiness, PostgreSQL, worker, Redis or end-to-end evidence. |

The existing backend virtual environment references a Python executable under another Windows user's directory (`C:/Users/OC/...`). Tests were run successfully using the bundled Python under the current user with the existing virtual environment's site-packages on PYTHONPATH. The virtual environment was not rewritten. Results reflect installed dependencies, not a fresh frozen dependency installation.

The failed backend test is `tests/test_content_branding.py::test_resaving_integration_options_keeps_stored_credentials`, line 403. Its initial Slack POST sends `credentials.api_key`, while current validation requires `access_token` and returns HTTP 400. The UI maps `bot_token` to `access_token`, and the runtime can read either key. This establishes a test/API contract mismatch; it does **not** establish that the current Slack UI flow is broken. Decide whether old API clients must remain compatible, then align validation and the regression fixture without weakening secret-preservation coverage.

## Feature comparison

“Covered locally” below means related backend scenarios passed in this audit, not that every control was clicked or every permutation tested. All browser and live-provider claims remain subject to the limitations above.

| Area | Reference scope found in Boosend | Nemio implementation and standing |
|---|---|---|
| Authentication/onboarding | Email/password, callback routes, magic callback, Instagram callback, recovery and setup | Signup/login/logout, email verification, password reset, invitations, workspace onboarding exist; related tests pass. Exact magic-link and Instagram-first sign-in parity is not established. |
| Workspaces/team | Workspace switching, settings, invitations, team membership | Tenant-scoped workspaces, roles, invitations, appearance, logo uploads and assignment notifications exist and have passing local tests. Browser usability needs revalidation. |
| Channel connections | Instagram, Facebook/Messenger, WhatsApp, Telegram | All four have implementations and passing adapter/OAuth/webhook tests. Real connect → inbound → delivered reply not verified here. LinkedIn is additionally gated on explicit platform approval. |
| WhatsApp | Accounts/profile/send paths and portal | Embedded Signup, own-account setup, templates, window restrictions and delivery receipts implemented and covered locally. Special templates, coexistence/history migration and calling are not established. |
| Simple/guided automation | Channel/post triggers, consent, follower checks, email capture, resource delivery and continuation | Equivalent major building blocks exist; guided runtime/compiler tests pass locally. Real provider behavior remains unverified. |
| Canvas/editor | Trigger/action/AI/condition/random/delay/wait/transfer nodes and configuration panels | Graph validation/execution, history, undo/redo, duplicate, import/export and AI generation exist. Backend runtime tests pass; current complete editor UX parity not verified. |
| Automation management | Lists, folders, activation, execution statistics, sharing | Search/status/account filters, folders, transfer/share, execution history and graph publication are represented; backend management/history tests pass. Browser bulk-action equivalence remains unverified. |
| Media automation | Text, voice, photos/video, avatar generation | Durable media, ElevenLabs/Inworld/MiniMax and HeyGen steps implemented; related local tests pass. Provider delivery/quality and paid-job outcomes unverified. Poppy is unavailable. |
| AI models/agents | Advanced agent, extraction, AI conditions and model nodes | OpenAI, Anthropic, Gemini and xAI adapters; simple mode, LangGraph, extraction, conditions, guarded tools, metering and fallback exist. Local agent/guard tests pass; real answer quality is not evaluated. |
| Knowledge/files | Text, website, PDF, Notion, Airtable, Notavo and reusable bases | Knowledge indexing, sources and scheduled sync exist; local source/indexing/sync tests pass. Notavo missing. Independent reusable-base/editor parity needs deeper comparison. |
| Inbox | Channel sessions/messages, composer, assignment, tags, notes and automation context | Unified inbox, identity/CRM linkage, notes, assignment, WebSocket updates, AI toggle and handoff implemented; backend tests pass. Current UI and real-time production behavior not established. |
| CRM | Contacts, custom fields, assignments, exports, execution/session inspection, segmentation | Lead CRUD/merge, tags/stages/custom fields, table/Kanban, segments, assignment, export and campaigns implemented; local tests pass. Compare scale/pagination and bulk operations before replacement. |
| Campaigns | Audience selection, campaign records and sending endpoints | Frozen audience and durable recipient delivery with permissions/window checks exist; local campaign tests pass. Real audience delivery/throughput unverified. |
| Integrations | Google/Microsoft, calendars, CRMs, marketing, voice/media, automation platforms and knowledge providers | 28 provider keys accepted by backend serializer, with operations distributed across dedicated adapters. This is not 28 complete or live-verified integrations. Slack contract regression exists; Notavo/Poppy unavailable; several reference providers have no direct backend key. |
| Booking | Google Calendar, Cal.com, Calendly, TidyCal and Zoho Bookings endpoints | Guarded availability/booking tools for Google Calendar and Cal.com exist. Calendly configuration UI exists, but backend integration allowlist lacks `calendly`; no equivalent keys for TidyCal/Zoho. Full provider parity absent. |
| Voice calling | Vapi/Retell nodes and agent/number discovery | Reusable agent creation, scheduled calls, private request/consent, callbacks and uncertainty handling implemented and covered locally. Actual calls and outcomes not verified. |
| Native forms | Rich question catalog, branching, themes, uploads, signatures and embedded booking | **Partial:** Nemio accepts only text, textarea, email, tel and select; 1–20 fields with mandatory email. Consent, CRM capture, idempotency, exports and post-submit actions work in local tests. Branching, binary uploads/signatures, richer question types, booking embeds and theme/layout parity absent. |
| Form-to-automation | Form actions and conversational collection | Nemio supports limited post-submit integration actions and signed `form.submitted` events. Arbitrary conversation-canvas execution for a form-only contact is not established as supported. |
| Link in bio | Rich editor/blocks plus product checkout and purchase-protected digital downloads | **Partial:** Nemio BioPage is title/bio/avatar/accent plus up to 20 links. Local publication/click behavior covered. No equivalent rich block/product-download fulfillment pipeline found. In-chat offers do not replace this feature. |
| Creator kit | Creator-facing pages/profile/offer tools | Nemio public kit, services/manual stats and approved Instagram follower refresh exist; local tests pass. Reach/engagement automation is not implemented; manually entered figures are not provider insights. |
| Instagram Insights | Separate account/post insights APIs: reach, profile views and post statistics | **Gap:** Nemio funnel/revenue/AI metrics are internal product analytics; they do not replace provider account/post Insights. Follower counts are only a subset. |
| Analytics/experiments | Dashboard and automation/contact statistics | Nemio funnels, revenue and A/B experiments implemented with passing local tests. Potential strength, but no measured comparison of accuracy, latency or conversion impact. |
| Tracking/deep links | Tracking links, click paths, deep links | Nemio deep links, UTM fields, daily aggregates and form attribution implemented with local coverage. Exact reference attribution/reporting parity not established. |
| Hate detection/moderation | Prompt-based rules, delete/reply, static/AI reply options | **Partial:** Nemio shield matches literal keywords and hides/deletes/flags. No equivalent prompt-based classifier or moderation reply action found. App description claims “toxicity rules” and “Team alerts” beyond what the inspected shield runtime demonstrates. |
| Website chat | Multiple widgets, sessions, messages, events and buttons | **Partial:** Nemio has a workspace-level widget/settings model, public session/chat and unified inbox integration with local tests. Multiple independent widgets and the full reference events/button configuration need parity work. |
| Payments/subscriptions | Subscription limits, trial/cancel, billing locks, Stripe methods/portal and product payments | Nemio plans/gates, credits/ledger, top-ups, Stripe subscriptions, offers, marketplace/Connect and reconciliation implemented; local tests pass. Historical genuine Stripe test callbacks cover only selected trial/plan/cancel cases. Failed payments, paid charges, metering, Connect and customer checkout acceptance remain separate. |
| Public API/MCP/connectors | OAuth/MCP server and integration endpoints | Nemio public API, MCP handlers, signed outbound webhooks and Zapier/n8n/Make packages exist with backend coverage. Published-directory/install acceptance and complete tool-scope parity not established. |
| Community forum | Posts, reactions, threads, pins and AI assistant UI | **Missing equivalent:** no Nemio forum route/model found. Support tickets/blog are different workflows. |
| Affiliate program | FirstPromoter-backed referral/campaign/revenue portal and tracking API | **Missing equivalent:** no Nemio affiliate/referral commission portal found. Marketing attribution is not affiliate accounting. |
| Platform operations | Reference admin/operational tooling requires a separate deeper inventory | Nemio has staff console, audit/security, plans, credits, support, growth/email configuration and backups. Local tests support many controls; superiority cannot be concluded from architecture alone. |
| Production operations | Owner reports reference is in production | Nemio production overlay, TLS edge and backup/restore scripts exist. Current deploy, public HTTPS, alert delivery, restore drill, load and live provider SLOs not verified. |

## Concrete source anchors

Boosend reference anchors, relative to its root:

- `lib/forms/types.ts`: rich question catalog, branching and theme definitions.
- `app/api/forms/[id]/branching/route.ts`, `app/api/forms/public/[slug]/upload/route.ts`, `app/api/forms/[id]/responses/[rid]/file/route.ts`: branching and upload/download paths.
- `app/api/products/create/route.ts`, `app/api/products/download/route.ts`: Stripe product creation and purchase-verified private file fulfillment.
- `app/insights/page.tsx`, `app/api/instagram/insights/account/route.ts`, `app/api/instagram/insights/posts/route.ts`: provider analytics.
- `app/hate-detection/page.tsx`: prompt rules and static/AI reply configuration.
- `app/forum/page.tsx`, `app/api/forum/assistant/route.ts`, `app/affiliate/page.tsx`, `app/api/affiliate/route.ts`: forum and affiliate features.
- `app/api/oauth/{calendly,calcom,zoho,microsoft,shopify,notion,google}/...`: reference provider scope.
- `components/nodes/`, `supabase/functions/automation-runner/`: workflow configuration and execution boundaries.

Nemio implementation anchors, relative to its root:

- `backend/apps/tools/forms.py`, `models.py`, `form_actions.py`: narrower forms and post-submit actions.
- `backend/apps/content/models.py`: simple BioPage shape and scheduled publishing model.
- `backend/apps/billing/payments.py`: conversation-linked offer checkout, distinct from digital-product fulfillment.
- `backend/apps/tools/shield.py`: literal keyword matching and hide/delete/flag runtime.
- `backend/apps/tools/creator_metrics.py`: follower count refresh only.
- `backend/apps/analytics/views.py`: internal funnel/experiment APIs.
- `backend/apps/crm/views.py`: provider allowlist and integration serialization.
- `backend/apps/crm/configuration.py`, `integrations.py`: credentials validation versus actual provider operations.
- `backend/apps/agents/tools.py`: advertised autonomous agent tools; no Shopify cart tool in the inspected schemas.
- `frontend/app/w/[workspaceId]/integrations/page.tsx`: catalogue availability and descriptions.
- `frontend/components/integration-configure-view.tsx`: provider setup forms; a setup form alone is not adapter support.
- `frontend/lib/apps.ts`: app descriptions; moderation copy overstates inspected runtime.
- `.github/workflows/ci.yml`: failing quality gates are required by CI, not optional recommendations.

## Copy/behavior discrepancies

1. Shopify catalogue copy advertises inventory/variant querying and generated carts. The inspected implementation provides Shopify knowledge ingestion; the autonomous tool schemas do not expose a matching cart operation. Treat advertised behavior as unsubstantiated until a real operation and test demonstrate it.
2. Comment shield copy advertises toxicity rules/team alerts; inspected runtime is keyword based and records moderation events. Align copy or build the promised behavior.
3. A Calendly setup form exists without a matching backend integration provider. Do not count it as working integration parity.
4. Old README/status tables contain historical phase statements and smaller test totals. They are not an accurate current readiness certificate. `PARITY_WORKLOG.md` is reverse-chronological and also retains old unresolved lists below newer completion entries; read dates and implementation together.

## Priority order to beat the reference

1. **Restore a reproducible green baseline:** resolve Slack API/test contract, Settings lint errors and strict warnings, formatting drift, relocatable Python environment, font build dependency and browser/Compose access. Run a frozen install and record exact dependency versions.
2. **Prove the core customer journey:** on PostgreSQL/Redis, test signup → connect → publish → real inbound → delivered reply → inbox/CRM → billing. Exercise retries, duplicate callbacks, disconnects, opt-outs, plan limits and cross-workspace access. Capture provider delivery IDs and receipt states with secrets redacted.
3. **Close high-value reference gaps:** rich forms with branching/uploads, bio commerce and digital fulfillment, provider Insights, moderation behavior, booking integrations and reusable knowledge UX. Explicitly decide whether forum and affiliate features belong in the launch scope; they remain gaps until delivered or deliberately excluded.
4. **Verify money and operations:** failed payment/recovery, metered usage and top-up reconciliation, Connect payouts/refunds, TLS/domain routing, backup restore, alert delivery, permission review and production-like load.
5. **Demonstrate improvement:** use matched scenarios and measure setup completion/time, send success/latency, duplicate side effects, agent task completion/hallucinations, cost per resolved conversation, accessibility and mobile completion, and operator recovery time. There is no measured evidence yet that Nemio beats Boosend on these outcomes.

No honest parity percentage can be assigned from route counts or passing test counts. The denominator must be a behavioral acceptance checklist, with each item classified as missing, implemented, locally verified, full-stack verified or live-provider verified.

## Remaining verification boundary

This is a broad source audit and fresh local backend/static validation, **not an exhaustive certification of all functionality**. The local reference may differ from its deployed production revision. Browser tests, PostgreSQL/Redis integration, external accounts, provider permissions, live billing, deployment/restore/load and detailed visual parity remain unverified in this session. Existing historical successes are useful supporting records but were not promoted to fresh results.

Application source was left unchanged; this report is the audit deliverable. Browser runner output is under ignored `.cache/audit-browser-*-results.json` and may be overwritten by future checks.
