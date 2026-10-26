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
