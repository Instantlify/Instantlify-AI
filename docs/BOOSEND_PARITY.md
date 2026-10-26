# BooSend functional parity — Nemio

Started 23 October 2026 (Asia/Karachi). This is a behavior checklist, not a claim of full parity.

**26 October update:** The latest implementation and outstanding verification are recorded in
`PARITY_WORKLOG.md`. The historical increment tables below describe the audit at their date;
media, AI steps, follow checks, tracked reminders, history, forms, creator pages, campaigns,
named CRM segments and additional provider adapters have since been implemented. Full parity
now also include reusable call-agent authoring, scheduled knowledge refresh, connected Instagram
follower statistics, native form-submission integration actions and the form.submitted event.
Full parity is not claimed: live delivery/callback checks, further creator metrics, arbitrary
conversation-canvas runs for form-only contacts, universal browser escape and the Notavo/Poppy
adapters remain outstanding. Detailed supported scope is in the current worklog.
The authorized BooSend account is a reference for read-only inspection. Nemio keeps its own
white/olive design. No customer contacts, account credentials, messages or vendor source code
are copied into Nemio.

## Evidence and delivery rules

- **Observed** means a control or workflow was inspected in the signed-in reference portal.
- **Source exists** means Nemio has code for it, but parity has not been established.
- **Verified locally** requires passing behavior tests, not just a working-looking control.
- **Live verification pending** means real provider delivery still needs its own evidence.
- Empty controls, preview-only switches and marketing claims do not count as functionality.
- Ongoing billing, subscription, settings and onboarding edits present at the start are preserved.

## Inventory

| Area | Reference behavior observed | Nemio status / remaining audit |
|---|---|---|
| Navigation | Workspace/account switching, Home, Automation, Integrations, Conversations, CRM, Apps, WhatsApp, Telegram, Settings | Source exists; account/channel views still need comparison |
| Home | Conversation/contact/AI-cost monthly charts, templates, search, bulk import, voice flow generation, Claude MCP | Source exists; real metrics versus illustrative data and bulk operations need audit |
| Automation list | Search, active/inactive/action-needed filters, creation choices, transfer, execution/reach stats; folders were visible during initial account loading | Source exists; account-specific behavior and folders need stable reference verification |
| Guided builder: channel | Instagram, Facebook, Telegram, WhatsApp; connected-account selection | First increment binds each generated graph to a selected account |
| Guided builder: triggers | Comment, direct message, story reply; specific, any and next-post selection | Specific posts checked against account ownership; next post resolves once from server activation time, shared across conversations |
| Guided builder: public comments | Optional public comment replies with rotating text | Durable, idempotent public replies and stable variation selection; separate from the one-private-reply allowance |
| Guided builder: consent | Opening message with a reply button; pause until interaction | First increment implements postback button and matching private-response wait |
| Guided builder: follow gate | Ask the lead to follow before resource delivery | Provider-backed follower verification pending; not represented as a working switch |
| Guided builder: email | Ask and collect email before delivery | First increment validates email, retries invalid replies, stores valid email in CRM |
| Guided builder: resources | Final message, multiple resource buttons, conditional follow-up for non-clickers | First increment supports 1–3 links; click-aware reminders pending |
| Guided builder: next steps | Optional tags, teammate assignment, continuation to another automation | First increment adds tenant-validated runtime actions; loops share a bounded step budget |
| Guided builder: save | Draft/active, Save, execution history, preview | First increment separates draft save/publication, retries publication without duplicate drafts, previews consent; full historical runs UI remains to audit |
| Advanced builder | Existing canvas, node palette, execution history, Test/Save/live state, duplicate/delete nodes, undo/redo, share template, AI builder, analytics | Core canvas exists; detailed action parity is tracked below; live Test/Save were not invoked |
| Conversations | Channel/search/tag filters, unread state, contact details, assignment, tags, notes, automation events, composer | Source exists; parity and provider behavior not yet verified |
| CRM | Search, campaign, bulk actions, table/Kanban, filters, segmentation prompt | Source exists; campaign workflows and segmentation configuration need audit |
| Integrations | Entry observed; shared reference explainer/configuration screens not yet audited in depth | Existing adapters/catalog do not establish 36+ fully functional integrations |
| Settings: profile | Name/email/photo, password, API key generation and documentation | Source exists; profile photo and connected identity behavior need audit |
| Settings: workspace | Create/switch, account and billing tabs, workspace name/color, sidebar colors, logo and brand name | Source exists; persistence of every branding field needs verification |
| Settings: team/subscription | Tabs observed | Existing billing work preserved; inspect and compare after that work is stable |
| Bundled Apps | Public reference describes forms, bio pages, calendar, tracking links, deep links, moderation, creator kits and website chat | Nemio has bio/calendar/deep links/moderation/web chat; forms, attribution links and creator kits need independent investigation and implementation |

## Increment 1: guided automations

Implementation covers account binding, nonempty specific keywords, reply-button opt-in,
validated email capture, resource links, tags, live workspace-member selection and continuation
to an enabled same-workspace automation. Assignments and continuations are checked again
at runtime, since permissions or destination availability can change while a flow is waiting.
Cross-graph continuation keeps the existing 100-step execution guard.

The canvas retains account scope and can inspect/edit the added node types. Imports retain
scope for explicit review; foreign accounts cannot be republished without rebinding. Existing
unscoped graphs retain their original behavior. No database migration is required.

Telegram receives inline reply/URL buttons. WhatsApp receives reply buttons and ordinary
clickable resource URLs. Meta postbacks with and without a message ID are deduplicated using
stable provider event facts. Provider-free tests establish transport payloads and local behavior;
they do not establish live Meta approval or real message delivery.

### Checks

- Backend: full local suite **477 passed, 9 skipped**. Focused automation/provider set **79 passed**; separate billing/plan checks **23 passed**.
- Frontend: guided compiler, validation, preview, failed-publication retry, phone layout and advanced-canvas round trip: **6 passed** in the browser.
- Production browser regressions: **16 passed** across guided automations, official brand icons, CRM contacts/inbox links, deep links, comment moderation and web chat settings. The landing check was rerun successfully after an initial connection refusal during service restart.
- TypeScript, changed-file ESLint, Ruff and production Docker builds passed. The local frontend, backend, worker and beat were rebuilt and restarted; backend, frontend and worker report healthy.
- These checks use local/mocked providers. Skipped tests, PostgreSQL-specific checks and real provider delivery remain pending.

## Next increments

1. Finish the advanced-builder and app-store reference audit; record each node's inputs,
   branching behavior, validation and side effects before implementing it.
2. Add individual/next-post targeting, public-comment reply rotation, follower verification,
   tracked link clicks and conditional reminders with signed-webhook/idempotency tests.
3. Compare knowledge bases, AI agents, integration actions, campaigns, inbox and CRM workflows.
4. Implement missing bundled apps as tenant-isolated vertical slices with public endpoint tests.
5. Run PostgreSQL regressions and provider sandboxes; record live verification separately.

## Advanced canvas inventory observed in the signed-in portal

The action picker was opened on an existing automation. No action was added and no live
automation was saved, tested, enabled, disabled or deleted. Mounted configuration panels
were inspected only as UI definitions; they are not evidence that every provider action works.

| Category | Observed choices | Nemio follow-up |
|---|---|---|
| Instagram | DM, voice, photo, video, generated avatar video | Text/buttons exist; media and generated-video graph steps need implementation |
| Condition | If/then, random path, continuation to automation, delay, wait for reply | Weighted binary random paths added, deterministic across retries; existing conditions/delay/wait/continuation retained |
| Actions | Email notification, add tag, set custom field, webhook request, assign teammate, contact stage | Fields and stages added; durable integration actions support CRM sync, Slack and Gmail; webhook response mapping pending |
| AI | Agent, data extraction, AI condition, ChatGPT, Grok, Gemini | Terminal agent handoff uses the durable metered AgentRun pipeline; extraction, AI conditions and standalone model nodes pending |
| AI voice | ElevenLabs, Minimax, Inworld, Poppy | Existing integrations are not proof of voice-node parity; inspect each schema and delivery path |
| AI calling | Category and Vapi/Retell configuration panels, allowed weekdays/time/timezone, custom/provider agent | Scheduling, consent, provider contracts, billing and retry semantics need a dedicated increment |
| Integrations | Email, Telegram, WhatsApp, Facebook, n8n, Make, Slack, Discord categories | Inspect each category without calling providers, then map to actual adapter operations |
| Webhook/n8n panels | Send-only versus response mapping; explicit test request | No reference test requests were sent; implement response mapping with outbound URL protections |
| Editing | Copy/paste, duplicate/delete, undo/redo, zoom/fit/interactivity, AI builder, share template | Compare each editor operation; do not equate a decorative control with implementation |

"On Assignment" is labeled coming soon in the reference trigger panel; it is not a delivered
reference feature. Account-specific reference lists can initially render cached data while
hydrating, so observations were rechecked after loading before assigning parity status.

## Provider contract references

- [Telegram inline keyboards](https://core.telegram.org/bots/tutorial#buttons-and-keyboards)
- [Meta WhatsApp reply buttons](https://www.postman.com/meta/whatsapp-business-platform/request/x0kd1at/send-reply-button)
- [Meta webhook reference](https://developers.facebook.com/docs/messenger-platform/reference/webhook-events/messaging_postbacks/)

The reference audit is incomplete. Nothing in this document should be read as "all BooSend
functionality has been replicated" until every outstanding row has implementation and evidence.

## Current continuation: automation actions, integrations and shorter homepage

- Added account-scoped post listing, selected/next-post targeting and public comment replies.
  Next-post scans only fixed account-owned endpoints with opaque pagination cursors and fails
  closed if publication chronology cannot be established. Publication resets the target.
- Added custom fields, CRM stages, random paths, integration jobs and terminal AI handoff.
  Integration jobs pause on interrupted/uncertain external execution instead of replaying sends.
- Corrected integration destination/options versus encrypted credentials, preserved existing
  secret values on partial saves, and removed hardcoded dummy credentials. Added actual Google
  Sheets append and Gmail send adapters plus scoped Google OAuth and verified sender identity.
  A failed OAuth attempt cannot become a successful-looking local connection.
- Shortened the homepage to seven sections with one interactive conversation preview, three
  benefits, a compact integration strip, live pricing, FAQ and a closing CTA. Moved the complete
  interactive tour/catalogue to `/features`; product-menu and footer links point there.
- Full local backend suite: **530 passed, 9 skipped**. TypeScript, Ruff, changed landing/test
  ESLint and production builds passed. Production browser coverage: **32 passed** (30 in the
  first run; two assertions corrected for accessible label text/trailing slashes and rerun).
- PostgreSQL full run: 536 passed and three environment/assertion failures. Isolated Stripe
  test credentials and removed dependence on deferred guard firing order; the affected suites
  plus automation/integration coverage then passed **129 tests** on PostgreSQL. This verifies
  the database isolation guards, but does not verify live Google/Meta messaging delivery.
- Updated frontend, backend, worker and beat are running locally; frontend/backend/worker
  report healthy. The homepage loads actual plan prices. No schema migration was needed.
