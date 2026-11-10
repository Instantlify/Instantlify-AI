# Boosend → Nemio implementation status

Updated 10 November 2026. This is the current implementation checkpoint. The comparison document records the earlier baseline. **Full functional parity and production replacement acceptance are not complete.** No completion percentage is justified by the current evidence.

The reference is `C:/Users/Jawad/Desktop/Boosend`; it was read without changes. Nemio changes are local and uncommitted. No deployment, customer messages, provider enrollments, payments or production database changes were performed. The source ledger inventories 496 screens, HTTP routes, edge functions and canvas nodes; these are source surfaces, not 496 independently verified features.

## Implemented and exercised locally

| Area | Actual behavior added or fixed | Evidence / limits |
|---|---|---|
| Form question types | Text, multiline, email, phone, choices, multiple choices, number, date, URL, yes/no, rating, opinion scale, upload, signature, welcome cards, grouped contacts, individual contact fields and calendar embeds | Schema, API and browser tests. Calendar embeds show provider pages; a form submission does not confirm an appointment. |
| Form paths | Forward-only exact-answer branching; hidden answers discarded server-side; required fields checked on the visible path; required contact capture cannot be bypassed | `test_form_branching.py`, `form-branching.spec.ts`; advanced reference logic still needs detailed mapping. |
| Form contacts | Optional CRM capture; grouped names/email/phone and explicit contact fields; tags; existing opt-outs preserved | `test_form_contacts.py`; a hidden optional phone cannot be forged into CRM. |
| Form presentation | Custom colors with readable contrast, button alignment, closed/published controls, HTTPS success redirects, configurable tags and contact capture | API validation and public UI; reference template/media/editor parity remains open. |
| Attachments/signatures | Bounded inline attachments in encrypted submission answers, safe filenames and checksums; private owner/admin download routes; PNG signature drawing/upload | `test_form_files.py` and browser upload/signature test. Up to 1 MiB each and 2 MiB combined. No public attachment URLs. |
| Responses and exports | Full streaming CSV/JSON, historical answers retained, secure attachment links, formula-injection protection, contact/multiple-choice display | Export regression covers 501 submissions rather than a truncated preview. |
| Form actions | Sanitized attachment metadata in downstream payloads; leadless internal notifications/webhooks; contact-required actions recorded explicitly; queued contact opt-out rechecked | Form action and integration suites. Provider responses are mocked. |
| Community | Shared authenticated forum, posts, edits/deletes by owner, threaded replies, votes, pagination, superuser pin/moderation, personal export | `test_community.py`, `community.spec.ts`; plain text is rendered safely. Private workspace data is excluded. |
| Community assistant | Bounded search of shared discussions, actual source links, untrusted-text instructions, explicit no-match response | Mock/fake-mode tests. Live model quality is not verified. Rich-text reference editor remains open. |
| Affiliate | Owner-bound FirstPromoter lookup, explicit enrollment, private server credentials, actual issued links/coupons/stats, unconfigured and verification states, duplicate prevention after uncertain responses | Five mocked backend cases plus browser flow. Signup/click attribution, commission/payment tracking and live provider acceptance remain open. No invented affiliate links. |
| Account settings | Persisted private encrypted profile photo; email format/uniqueness validation and reverification after changes; password policy enforcement, refresh-token revocation and other-session invalidation | Four account backend cases and browser upload/reload/remove flow. Existing access tokens retain their configured expiry. |
| Messaging | Per-conversation sequence for identical timestamps; row-lock allocation; webchat returns latest 200 messages instead of oldest 200 | Ordering and long-thread regressions pass. PostgreSQL concurrency case is skipped on SQLite. |
| Integrations | Legacy Slack API-key compatibility while keeping current access-token handling; visible connection count, webhook delivery log and newly issued token | Existing regression suite; real provider delivery unverified. |
| Frontend/build | Local licensed variable fonts remove build-time font-network dependency; strict lint/type errors resolved; readable action contrast; mobile preview no longer covered by support widget; public form embed policy enabled | Production build and static gates pass; complete browser result recorded below when available. |

## Validation

- Full backend suite: **866 passed, 10 skipped** on SQLite, 51.79 seconds. Output: `.cache/parity-backend-final.txt`.
- Affiliate hardening follow-up: **5 passed** after link validation and ownership error handling changes.
- Ruff lint and formatting: pass.
- Django migration drift: no changes detected with test settings.
- Frontend TypeScript and ESLint with zero warnings: pass.
- Production frontend build: pass, including standalone packaging.
- New affiliate/profile browser tests: **2 passed** against local Chrome with API fixtures.
- Full production browser regression: **143 passed, 8 skipped, 0 failures, 0 retries/flaky cases**, 248.82 seconds; see `.cache/parity-browser-production.json`. The follow-up file-selection timing fix is checked separately below.
- Docker Linux engine remains unavailable (engine pipe missing), including outside the sandbox. Fresh PostgreSQL, Redis, worker and complete real-service onboarding acceptance are not established.
- Browser tests use mocked backend/provider APIs. Backend tests exercise Django APIs and persistence using test settings. Neither proves successful production provider delivery, payouts or live AI answer quality.

## Schema and release considerations

New migrations:

- `tools/0005`–`0007`: form branching, presentation/closure/tags and optional contact capture.
- `platform_ops/0011`: shared community posts/replies/votes.
- `platform_ops/0012`: affiliate account binding and enrollment state.
- `tenants/0012`: private profile photos.
- `crm/0012`: message sequence backfill and uniqueness constraint.

Apply migrations in a tested staging release before starting the matching backend and workers. Message backfill orders legacy records by conversation, timestamp and ID: it cannot recover the true historical order of records that already share a timestamp. Validate backfill duration on a production-sized copy and PostgreSQL locking before release. Do not run a mixed old/new writer deployment during sequence rollout.

Affiliate settings are documented in `.env.example`: FirstPromoter API key, account ID, optional campaign, currency and revenue divisor. These are platform configuration, not tenant-supplied browser secrets. The divisor defaults to 100 to match the reference UI; confirm actual provider currency/amount semantics before enabling. Existing Boosend promoters are deliberately not claimed by email alone; migrating them requires an explicit verified ownership mapping.

## Remaining work required for the requested complete parity

1. Map each source-ledger entry to concrete behavior and negative cases. Most entries still require individual behavior mapping; broad feature labels and passing suites are insufficient.
2. Rich bio blocks, templates, product catalog, checkout, purchase entitlements and protected digital downloads.
3. Instagram account/post Insights using the currently supported provider permissions and metrics, with live acceptance.
4. AI comment moderation and moderation reply actions beyond keyword-based shield rules.
5. Missing provider adapters and exact option parity, including Notavo/Poppy and full Calendly/Zoho/TidyCal workflows. A calendar iframe does not complete these integrations.
6. Affiliate click/signup attribution, payment/commission events, account migration, and verified provider data semantics.
7. Remaining advanced form/editor layouts, welcome media, theme/template interactions and branching options; detailed comparison is still needed.
8. Exact authentication/magic-link/Instagram-first signup behavior, advanced automation/canvas option parity, marketplace/template edge cases, special WhatsApp workflows, and provider-specific UI controls need acceptance against the reference rather than assumption.
9. Live channel connect → inbound → automation → delivered reply across supported channels, provider error/retry scenarios, live billing and AI/media execution.
10. PostgreSQL/Redis/worker checks, migration rehearsal, load/capacity checks, backup/restore validation and production deployment acceptance.

There is no basis yet to declare Nemio better overall than the running Boosend service. The changes improve specific tested behaviors; the remaining comparison and operational evidence must be completed before replacement.
