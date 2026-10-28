# Saved workspace appearance — 28 October 2026

- Workspace primary color now controls the actual client shell, actions, active navigation
  and message accents. Saved sidebar background/text colors are persisted in branding and
  applied only inside that workspace; switching workspaces restores the selected theme.
  Light accents choose readable action text, and low-contrast sidebar combinations receive
  an inline validation message. Public pages keep the default Nemio palette.
- Settings saves workspace name and branding together in one transaction. Sidebar values
  are included in saves and reloads, color inputs have field validation and labelled swatches,
  and only owners can edit appearance. Existing agency branding inheritance is preserved.
- Replaced the logo's temporary data-URL preview with a real image upload. PNG/JPG/GIF/WebP
  files up to 5 MB are stored durably in the database and served from a versioned image URL.
  Invalid formats/oversized files are rejected; logos can be replaced or removed without
  losing the saved theme. Workspace JSON never includes the binary image data.
- Migration tenants.0009 is applied locally. Full PostgreSQL suite: 723 passed. The five
  new browser cases passed for save/reload, cross-workspace isolation, validation, uploaded
  logos, owner permissions and bright accents; 16 existing navigation/validation cases also
  passed. Production build/TypeScript, focused lint and backend checks passed. Settings
  retains its seven pre-existing lint errors; no clean full-file lint claim is made.

# Product-tour header contrast — 28 October 2026

- Corrected the detailed product-tour header's translucent surface to white so the navy
  logo, navigation links and sign-in control remain readable. The home and tour headers
  now share the same contrast treatment. Softened the home header border and AI preview halo.
- All 17 public-page browser checks passed; desktop review confirmed a white header with
  navy logo/text on the product-tour page.

# White, navy and neon theme — 28 October 2026

- Replaced the ivory/olive brand palette across landing/feature pages, authentication,
  onboarding and the client portal. Shared surfaces are white and cool blue-white, primary
  controls/headings use navy (#10244a), and small highlights use neon lime (#c3ff5c).
- Moved hard-coded legacy brand colors onto shared tokens, including menus, cards, form
  fields, pricing, public demos and onboarding artwork. Navy active sidebar items have a
  neon marker; inbox AI/automation/team messages use distinct navy/slate tones.
- Neon is limited to accents and the final landing CTA. That CTA uses navy text with a
  measured 14.4:1 contrast ratio. Brand/channel icons, status meanings, custom customer
  branding and the supplied animated logo remain available.
- Desktop/mobile visual review covered landing, feature tour, signup, onboarding, portal,
  expanded navigation and inbox. Fixed an Automations header overflow exposed during mobile
  navigation by allowing its title and tabs to wrap on small screens.
- Final production build/TypeScript, focused lint and all 34 public/onboarding/client/navigation
  browser checks passed. Updated frontend is running locally; application services are healthy.

# WhatsApp onboarding and approved messages — 27 October 2026

- Added a dedicated Connect WhatsApp flow using Meta Embedded Signup. One-use state is
  scoped to the signing-in user/workspace; the backend validates the token's app, permissions,
  shared business account and phone ownership. Tokens remain encrypted. Number registration
  and business-account notification subscription resume from durable checkpoints; reconnects
  preserve conversation history and recheck account limits/locks.
- Added an own-account developer path to the advanced channel form using the phone number
  ID, business account ID and token from Meta API setup. This path can use Meta's real test
  number before an Embedded Signup configuration is available. Number ownership is checked,
  notifications are subscribed and unregistered numbers offer Finish WhatsApp setup.
- WhatsApp inbox conversations can load approved templates, validate required text/media/link
  details and customer consent, preview the message and queue it outside the ordinary 24-hour
  window. The sender checks approval and the exact definition again before delivery. Opt-outs,
  rate limits, connection expiry, platform controls and ambiguous-delivery protections remain.
  Ordinary replies stay closed until a customer responds. Special template formats are shown
  as unavailable; template authoring/approval remains in WhatsApp Manager.
- Signed sent/delivered/read/failed callbacks update inbox progress without creating inbound
  customer messages. Receipt processing handles duplicates, ordering and a receipt arriving
  before the send transaction commits. Frontend /webhooks forwarding enables one HTTPS
  tunnel to cover the local portal and callback route.
- Final PostgreSQL regression suite: 711 passed. Production frontend build/TypeScript,
  focused lint, backend lint/format, Django system checks and migration drift checks passed.
  The 26 browser checks for WhatsApp/inbox/validation passed on local production port 3000;
  an additional own-account setup browser check passed. Migration channels.0006 is applied,
  and backend, frontend and worker report healthy.
- No live WhatsApp messages were sent. Meta credentials, a public HTTPS callback and an
  authorized recipient are still needed for provider acceptance; old WhatsApp app history,
  coexistence migration, calling and special template formats are outside this increment.
  See docs/WHATSAPP_LOCAL_SETUP.md for precise local setup and live verification steps.

# Landing Product menu dismissal — 27 October 2026

- Product dropdown closes on page scroll, pointer clicks outside it, any header link
  activation and Escape. Escape returns keyboard focus to its trigger; native details
  toggling and product links retain their behavior. Event listeners are cleaned up on unmount.
- Production frontend deployed locally; build/TypeScript and focused lint passed.
  All five landing-logo/menu browser checks passed.

# Validation and supplied brand asset — 27 October 2026

- Shared client form validation now covers the existing form screens and their controls:
  required markers, inline field messages/outlines, first-error focus, whitespace checks,
  email/link formats, text lengths, numeric limits and required permission checkboxes.
  Errors clear as the affected field is corrected; server errors are scoped to the submitting
  form and use readable field names instead of API keys or nested response objects.
- Form creation suggests an available public address and explains the resulting link.
  Internal answer names are under Advanced; mandatory contact email is protected, duplicate
  answer names and empty dropdown choices are checked before saving. Plain-language option
  labels replace text/textarea/tel/select. Password settings now match the backend's 12-character
  rule and show confirmation mismatches beside the confirmation field.
- Integration setup highlights every missing required value and malformed email/web address.
  API errors translate slug to public address, explain missing values and invalid choices,
  and avoid raw server failures or technical nested object output.
- Copied the owner's supplied nemio_ai_logo_v2.gif unchanged into public/brand. The shared
  default Nemio mark uses the full animation with readable brand text; custom workspace
  branding is preserved. Landing header/footer logo clicks return to the top without a reload,
  respect modified-click navigation and use instant scrolling for reduced-motion preferences.
- Production build/TypeScript and focused shared-component lint passed. All 51 production
  browser checks passed across validation, publishing, integrations, CRM, automation setup,
  logo scrolling and workspace navigation. After a logo fitting adjustment to remove clipping,
  all 19 affected logo/navigation/validation checks passed again on the final local build.
- Broader changed-file lint still reports the seven pre-existing Settings errors (explicit-any
  and state-in-effect rules), confirmed against HEAD before these edits; no clean full-lint
  claim is made. No backend validation or access restrictions were removed.

# Workspace navigation update — 27 October 2026

- Sidebar and Settings workspace switches open the selected workspace's Home screen.
- Desktop navigation starts as a 76px icon rail and expands on hover or keyboard focus.
  Expansion overlays the page, keeps icons on the same rows and respects reduced motion.
  Open account/workspace menus stay usable; workspace menus dismiss outside or with Escape.
- Mobile retains its full navigation drawer; choosing a workspace closes the drawer.
- Production frontend deployed locally. All 13 navigation/client browser checks passed,
  including keyboard access, workspace switching, channel selection and app pin/unpin.
  Production build/TypeScript and changed-component lint/format checks passed.

# Current continuation — 26 October 2026

Remaining-feature implementation continuation (deployed locally):

- Reusable custom call-agent authoring for Vapi and Retell: instructions, greeting,
  provider model/voice and duration. Durable, idempotent creation jobs publish Retell agents,
  preserve confirmed IDs after partial failure and do not replay uncertain creations.
  Selecting an agent as the integration default is a separate explicit action.
- ZorroMail transactional email adapter and configuration are now available. Uses the
  provider's documented idempotency header, verified sender options and suppression results;
  acceptance is not represented as confirmed delivery.
- Creator kits can select real connected Instagram accounts for hourly provider-sourced
  follower counts. Public metrics show their account and timestamp. Manual reach/engagement
  figures remain separately labelled; those metrics are not automatically retrieved.
- Forms can queue up to five integration actions per new consented submission: confirmation
  email, CRM sync, Slack notification or n8n/Make/custom webhook. Jobs link to the submission,
  recheck opt-outs, active form/integration and plan, and expose action status in responses.
  Duplicate request IDs do not queue duplicate actions. Added the signed form.submitted event.
  These are native form actions and webhook triggers, not arbitrary conversation-canvas runs.
- Focused backend checks: 108 marketing/guided checks; 30 call/marketing/integration checks;
  23 creator/tool/export checks; 46 form/call/integration/export checks passed.
- Browser source checks: eight creator/form/integration/knowledge scenarios passed across the
  main run and focused form-test retry. The full PostgreSQL suite passed 670 tests; a final
  optional-sender-name email fix passed its nine affected tests afterward.
- Final production build and TypeScript passed. Tools 0003/0004 and CRM 0008 migrated locally;
  backend, worker, beat and frontend deployed. All eight production browser checks passed.
  Worker reports the creator-statistics and knowledge-sync tasks registered; services healthy.
- Requested official Notavo/Poppy API documentation and sandbox accounts for live provider
  and billing verification. Neither request is authorization to send real customer messages.
- The owner confirmed local-only operation and authorized Stripe test forwarding. Added a
  secret-scrubbing Stripe CLI helper and opt-in isolated verification command. Genuine signed
  callbacks now reconcile trial creation, update, Starter → Pro → Starter plan changes and
  cancellation. Fixtures have no memberships/email recipients and are canceled afterward.
  Existing workspaces/subscriptions and registered Stripe destinations were not modified.
- Real callbacks revealed SDK objects no longer providing dict.get; recursively normalize
  verified events, retrieved subscriptions and invoice previews before domain processing.
  Protect ongoing trials against paid zero-value creation/plan-change invoices arriving late.
  Real SDK signature/deduplication/object tests and invoice-order regressions cover the fixes.
  See LIVE_PROVIDER_VERIFICATION.md for repeatable local setup and remaining sandbox scope.
- Final billing continuation verification: 682 PostgreSQL tests passed; 122 focused billing,
  payment, marketplace and operations checks passed before the final trial-order additions,
  followed by 38 affected checks. Full backend Ruff lint/format and Django system/migration
  checks pass. Formatted eight generated migrations and one existing view to satisfy the
  repository-wide CI formatter. Final real Stripe run: eight events acknowledged with HTTP 200;
  paid zero-value trial invoices ignored, subscription events processed, fixture canceled.

Provider contracts used: [Vapi assistant creation](https://docs.vapi.ai/api-reference/assistants/create),
[Retell agent creation](https://docs.retellai.com/api-references/create-agent),
[Retell response-engine creation](https://docs.retellai.com/api-references/create-retell-llm),
[Retell publication](https://docs.retellai.com/api-references/publish-agent),
[ZorroMail transactional API](https://www.zorromail.app/docs/transactional).

Automatic knowledge syncing continuation:

- Added opt-in hourly, six-hourly and daily schedules for connected Sheets, Airtable,
  Notion and Shopify sources. The existing agent dispatcher queues durable, leased refreshes.
- Refreshes recheck feature entitlements, discard results after disabling or changing source
  settings, preserve existing documents on failure, and recover interrupted workers.
  Unchanged content avoids another embedding run; changed revisions use existing metering.
- Integration cards expose schedule/frequency, pause, last successful source refresh, next
  refresh and failures. Indexing progress remains in AI knowledge settings.
- Focused backend regression: 39 passed. PostgreSQL source/sync/tenant isolation: 20 passed.
  Browser enable/frequency/pause passed; existing integration configuration checks: 2 passed.
- Migration agents 0011 applied locally; all four service images rebuilt and deployed.
  The automatic-sync browser check passed again against localhost:3000.
- This closes the manual-only knowledge-refresh gap in source. It does not complete the
  remaining call-agent authoring, creator statistics, form-trigger or provider-live checks.

Automation UI regression correction:

- Three-dot controls now open Edit/Duplicate/Delete actions instead of navigating.
  Deletion requires confirmation, preserves the row on server failure and removes only
  the selected row after a successful DELETE. Escape/outside clicks dismiss the actions.
- Restored the simple builder's six-step timeline and channel-specific trigger cards.
  Restored a live phone frame with Instagram, Messenger, WhatsApp and Telegram themes,
  current account/message content, interactive consent/replay and a mobile preview toggle.
- TypeScript and changed-file lint passed. Guided/management browser checks: 16 passed;
  four expanded management checks passed, including duplication and keyboard dismissal.
  Production frontend build passed and was deployed to localhost:3000. All four management
  checks passed again against that production build; desktop/mobile screenshots inspected.

The user resumed implementation and authorized the GitHub push previously requested.
BooSend is strictly read-only: no records, drafts, settings, messages or automations were
created, removed or saved there. Opening the CRM segmentation dialog exposed named
segments with a name and prompt; Nemio now implements this rather than only fixed intent tags.

Current additions (source; release verification in progress):

- Campaign drafts, account selection, compose/audience/review, optional link buttons and
  photo/video URLs, selected/filtered audiences, scheduling, idempotent launch, guarded
  durable delivery, cancellation of unqueued recipients and per-recipient results.
- Named AI contact segments with editable criteria, pause/delete, managed contact tags,
  metered classification and invalid-output rejection; existing sales-intent classification retained.
- Outlook sending, MailerLite group sync, Klaviyo profile/list membership and Systeme.io
  contact creation/matching. Existing provider unsubscribes are not silently reactivated.
- Manual Jotform contact imports with region/question mapping, repeated-import matching,
  plan contact caps and preservation of existing opt-outs. Imports do not create conversations.
- Bounded Sheets, Airtable, Notion and Shopify knowledge snapshots, refresh without duplicate
  documents, indexing protection and separate usage records for changed source revisions.
- Vapi/Retell optional final-outcome polling; polling never recreates a call. Provider summaries
  can feed subsequent steps. Saved provider agents are still required.
- Animated seven-section landing page: conversation autoplay, pause, pointer tilt, floating
  channel marks, product illustrations, scroll reveals and reduced-motion/visibility handling.
- Plan enforcement extended to manual contact creation, inbound first-contact creation,
  custom segmentation updates/execution, knowledge uploads/indexing and avatar generation.
  Inbound events blocked by a contact cap stay pending without exhausting poison-event retries.

Verification at this checkpoint:

- Campaign backend: 5 passed. Marketing/campaign/integration set: 17 passed.
- Calls/voice-related inbound set: 23 passed. Knowledge/inbound set: 20 passed.
- Recent segmentation/import/knowledge/credits focused set: 44 passed.
- Full SQLite run: 628 passed, 9 skipped, one export registration failure; registration corrected.
- Production browser regression: 39 passed initially; two navigation timing failures during
  the image build and one textarea label selector failure. The three focused reruns passed
  after deployment and the selector correction (42 scenarios passed across these runs).
- Full PostgreSQL regression: 640 passed. The export registration fix is included.
- Affected plan/CRM/channel/export checks: 42 passed. Later credit/segment/knowledge/avatar
  checks: 27 passed; final credit-revision/segment/Snapchat checks: 7 passed.
- Final production images built successfully, including frontend TypeScript validation.
- Final images deployed locally; migrations through agents 0010 and CRM 0007 applied.
- Implementation is committed in 9cb437b, verification notes in 443e262 and the browser
  correction in b698c66. GitHub accepted the push of main through b698c66 after local sign-in;
  HEAD and origin/main matched. This verifies publication, not full functional parity.
- The worker answered a direct Celery ping while its ten-second Docker probe timed out.
  The probe now allows Django CLI startup plus the reply window, with a startup grace period.
- Plan restrictions read the configured catalogue, including billing-period AI message caps,
  feature flags, account/contact/seat limits and billing status for paid AI execution. The
  current paid tiers share feature flags and differ in allowances; this is catalogue policy.

Known scope limits, which must not be represented as completed parity:

- Live provider credentials/delivery and billing-provider callbacks are not verified by mocks.
- Notavo and Poppy still need usable official API contracts. ZorroMail now has a native adapter.
- Reusable call agents can now be authored in Nemio. Per-call transient agent definitions are not implemented.
- Knowledge sources now support opt-in scheduled refreshes; live provider validation remains.
- Connected Instagram follower counts are provider-sourced; additional creator metrics remain manual.
- Tracking links use HTTPS redirects; automatic escape from every in-app browser is not implemented.
- Forms trigger native integration actions and form.submitted webhooks; arbitrary conversation-canvas runs are not supported for form-only contacts.
- The full reference audit remains incomplete where the reference account has no records.

## Historical checkpoints below (superseded where the current notes differ)

# Active parity implementation

User scope: finish the remaining BooSend functionality in Nemio, independently designed UI.
Do not stop at another partial milestone. Continue implementation and verification; distinguish
mock/provider-free checks from live provider verification. Keep reference inspection read-only.
Latest explicit instruction: continue until complete, then push ALL project code to GitHub.
Remote is https://github.com/JawadTarar33/Nemio-AI.git, current branch main. No push yet.
Do not end the task after another partial batch; the user explicitly objected to that.

## Active continuation (23 October, current source)

The source now includes the following, awaiting the deployment running in this turn:

- Image/video/audio nodes and inbox media links, bounded HTTPS URLs, private-reply guards.
- Canvas undo/redo/copy/paste/duplicate; test walkthrough, JSON template import/export.
- n8n/Make/Discord/custom webhooks with pinned public-IP transport and response mapping.
- Durable, metered AI generation/extraction/conditions and terminal agent handoff.
- Verified Instagram follow gate; unknown provider status stops for review.
- Opaque resource links, click attribution, per-run reminders with send-time cancellation.
- Durable per-run history with transition metadata, legacy backfill and no customer text in traces.
- Forms: custom fields, public/embedded pages, encrypted responses, consent, CRM capture,
  idempotent submission, exports and preservation of existing opt-outs.
- Tracking app: UTM tags, daily aggregate counts and form attribution; no visitor-IP storage.
- Creator kits: real saved profiles, entered audience figures, links/offers and public pages.
- Voice steps: ElevenLabs/Inworld/MiniMax, provider-owned credentials and paid generation once.
- Vapi/Retell call steps: actual private call request, captured phone, weekdays/timezone/window,
  opt-out recheck, durable dispatch. Accepted does not mean answered/completed. Saved agents only.
- HeyGen v3 avatar video: create once, safe polling, render timeout, guarded private video delivery.
- New encrypted payloads participate in workspace export and retention policy.

Evidence:
- Full SQLite backend: 603 passed, 9 skipped. Additional legacy migration regression: 3 passed.
- Calling/voice/avatar focused contracts/runtime: 14 passed. Earlier guided/voice set: 101 passed.
- Forms/creator/tracking browser workflows: 3 passed after fixing long-dialog scrolling.
- TypeScript passed. New/changed feature ESLint rerun running after fixing a purity warning.
- Full PostgreSQL test build/run running in exec session 18546 (image before final legacy-backfill
  collision fix; rerun affected migration test against rebuilt test image afterwards).
- Production Docker build running in session 45560; includes current migrations/backfill fix.
- Preview port 3001 session 9728 stopped; next-env.d.ts restored to production types path.
- DB requires automations 0006/0007/0008 and tools 0002. Stop old backend/worker/beat before
  migrating: old processes cannot write the new non-null run_token column. Then migrate with
  new backend image and restart all four services. No data/volumes are to be deleted.
- Git remains main, no commit or push yet. User explicitly authorized pushing ALL code when done.

Remaining implementation/audit:
- Finish remaining provider adapters and reference audit of CRM/inbox/campaigns/settings/dashboard.
  Many integration catalogue entries still have no live adapter; do not claim all are complete.
- Calling uses saved provider agents; custom/transient agents and call outcome callbacks not yet built.
- Advanced Test/history/new action browser coverage and full production regressions still needed.
- Structured AI steps should have explicit deterministic local-test provider outputs (currently fake
  provider gives generic text and extraction/condition correctly stop for review).
- Live provider credentials, permissions and real delivery are unverified. No real calls/messages
  were placed in BooSend or provider accounts. Reference app menu button still exposes no choices.
- Do not end at this batch. Continue all independent work, then final verification and GitHub push.

## Current changes (deployed locally)

- Specific-post selection, ownership verification, account posts API, webhook post IDs.
- Public comment reply variations through durable deliveries; public replies cannot consume
  Meta's one-private-reply allowance. Opt-out, rate limits and ambiguous sends covered.
- Next-post targeting: server activation time, account-owned pagination, shared target resolution,
  reactivation clears prior target. Backend tests pass; UI/compiler/canvas controls added.
- Advanced custom fields, contact stages and binary weighted random paths. Runtime tests pass.
- Integration action and terminal AI assistant handoff use durable IntegrationJob and AgentRun
  workers. Runtime, interrupted-worker, opt-out and tenant isolation tests pass.
- Google Sheets/Gmail adapters and scoped OAuth added; credential/options mapping corrected.
  Partial saves preserve encrypted secrets and OAuth failures stay failures. Added browser tests.
- Homepage shortened to seven sections, one demo, three benefits and a compact integration strip;
  full interactive product tour and catalogue moved to /features.

## Verification so far

- Latest full backend suite: 530 passed, 9 skipped.
- Guided browser suite after specific-post/public replies: 9 passed on preview port 3001.
- Focused guided backend after next-post/custom-field/stage/random paths: 61 passed.
- Latest TypeScript passed. Changed-file ESLint has no errors, existing integration-page warnings.
- Production browser checks: 32 passed (30 initial + 2 corrected selector assertions rerun).
- PostgreSQL follow-up: 129 passed across automation/integrations, tenant guards and affected
  metrics/growth suites. Full initial PostgreSQL run had 536 passes and three test setup/assertion
  failures, now corrected. Test settings cannot inherit deployment Stripe credentials.
- Separate local preview port 3001 was stopped. Production Docker build passed and all four
  updated services were restarted. Frontend, backend and worker report healthy.
- Production port 3000 contains the current increment, shorter homepage and white MCP fix.
- No migrations were needed for the current automation work. Running DB already has the
  independent billing migration 0007. Preserve all other chats' billing/onboarding edits.

## Remaining workstreams

1. Finish current automation actions and add media, AI model/extraction/conditions,
   agent handoff, follower checks, link-click tracking and conditional reminders.
2. Continue auditing the remaining integration adapters/provider contracts. Credential/options
   separation, Stripe key mapping, default/dummy credential removal, Sheets/Gmail OAuth and
   actual Sheets/Gmail operations are implemented and covered by tests. Live providers remain
   unverified; do not substitute successful-looking stubs.
3. Advanced editor history, test, undo/redo/copy/duplicate, sharing, analytics comparisons.
4. CRM/inbox/campaign/settings/dashboard audit and fixes.
5. Missing forms, tracking and creator apps after reference investigation.
6. Full backend/browser production regressions, PostgreSQL checks, live-provider checks.

## Reference access

The authenticated BooSend session still works in the in-app browser. Temporary audit tab 8
is bound as `parityAudit` in cua_repl, currently on inbox after inspecting navigation. Apps
button expands no visible choices in the collapsed sidebar; do not invent app behavior.
Original reference URL https://app.boosend.ai/ . No live reference flow was edited or sent.

## Known implementation follow-ups

- Integration/AI handoff/interrupted-worker tests pass. Browser regressions added for next-post
  compiler behavior, incremental post-ID typing, token-preserving edits and OAuth failures.
- Finish lint/format/full tests after subsequent changes. New action runtime raises generic
  validation failures into conversation state; preserve no automatic replay after uncertain
  external side effects.
- Read `docs/BOOSEND_PARITY.md` for the observed reference inventory and honest gaps.
