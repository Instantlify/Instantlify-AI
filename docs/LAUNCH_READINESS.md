# Launch experience improvements — 2026-09-21

Implemented:

- Two visible setup steps; team, integrations and billing are deferred. An explicitly selected pricing plan is preserved and opens Payments after setup.
- Pricing-answer, enquiry-qualification and booking-link starter forms create drafts for review. They never publish automatically. The booking starter shares a link; it does not claim to confirm an appointment.
- AI answer preview uses saved settings and ready knowledge, checks access and credits, and records usage. It never creates conversations, sends messages or executes tools. It tests single-turn answers and keyword handoff only, not the complete sales agent workflow. Live previews consume credits; supplied documents are identified without claiming verified citations.
- Expiring password reset links, password validation, CSRF protection, throttling, single-use tokens, refresh-token revocation and session invalidation. Existing access JWTs retain their normal short expiry.
- Unique inbound lead counts across comments and DMs. Conversion percentages require the same lead to reach the preceding stage first within the selected period. Entry channels are not presented as sequential conversions.
- Simplified navigation, outcome-focused homepage/dashboard, public help, and configurable policy/contact links.

## Deployment configuration

Set `NEMIO_PRIVACY_URL`, `NEMIO_TERMS_URL` and `NEMIO_SUPPORT_EMAIL` in the deployment environment before building the frontend. Compose passes these as build arguments and runtime environment variables. Rebuild when they change: the help page is prerendered, while the homepage is rendered on demand. Use actual published HTTPS policy URLs; no placeholder legal documents have been created.

Password recovery uses the existing `EMAIL_*`, `DEFAULT_FROM_EMAIL` and `PUBLIC_APP_URL` settings. Check the app URL is the public HTTPS origin and verify delivery to an actual mailbox. Links expire after one hour. The reset secret is in the URL fragment and is removed from browser history after reading.

Deploy backend and frontend together because the analytics response now includes `unique_leads` and nullable conversion rates. No database migration is required.

## Verification

- Full backend regression: 408 passed, 9 skipped (SQLite/local test settings). PostgreSQL-only checks are not established by this result.
- All 14 browser scenarios passed across the final targeted runs. They use mocked APIs and cover marketing, plan selection, onboarding, navigation, mobile layout, recovery, draft creation and AI preview; they do not prove external-provider acceptance. Desktop and mobile screenshots were inspected.
- Next.js production build and TypeScript passed. Frontend and backend lint passed; no pending migrations were detected.

## Launch-blocking gaps closed since — 2026-09-23

- **Caller address behind the proxy.** Django read `REMOTE_ADDR`, which is the edge
  proxy for every production request, and DRF fell back to the caller's own
  `X-Forwarded-For` for anonymous throttle keys. `TRUSTED_PROXY_DEPTH` now names the
  hop count, Caddy and nginx overwrite the header instead of appending, and production
  refuses to start at `0`. Set `TRUSTED_PROXY_DEPTH=1` in the deployment environment.
- **Email verification.** Signup sends an expiring confirmation link; `/api/auth/me/`
  reports `email_verified`; unconfirmed signups that never joined a workspace are
  released after `UNVERIFIED_SIGNUP_DAYS` so they stop holding someone else's address.
- **Welcome credits.** `platform_credits` workspaces started at a zero balance, so the
  first thing a new signup met was a card form. Confirming the address now grants
  `SIGNUP_CREDIT_CENTS` once per workspace. Agency client workspaces are excluded,
  because their balances resolve to the parent.
- **Production stack.** `compose.prod.yaml` puts Caddy in front as the only public
  service, switches Django to production settings, keeps Flower behind a `debug`
  profile and runs a `pg_dump` backup service. `deploy/restore.sh` restores a dump and
  refuses to run without explicit confirmation. See the README's deploying section.
- **LinkedIn.** The adapter posts to an endpoint LinkedIn does not grant ordinary apps.
  Connecting is now declined unless `LINKEDIN_MESSAGING_APPROVED` says the grant was
  confirmed against a real account, rather than accepting a channel that would fail
  every send.

Still unverified in this increment: the Caddyfile and nginx changes have not been run
through `caddy validate` or `nginx -t`, and no restore has been rehearsed against a
real dump. Do both before the first deploy.

## Required before accepting paying clients

1. Prove connect → real inbound enquiry → delivered reply on each advertised live channel. Confirm the actual provider approval status; repository code is not evidence of approval.
2. Verify real AI knowledge retrieval, appropriate refusal on unknown facts, and human handoff. Exercise bookings/payment tools separately from the safe answer preview.
3. Complete Stripe sandbox purchase, renewal/cancellation and webhook acceptance. Confirm displayed pricing and credit behavior match actual billing.
4. Run PostgreSQL/pgvector tests and the Compose end-to-end suite on the release build; check HTTPS routing, alerts and backup restoration.
5. Publish accurate policies, configure their URLs and public support contact, and verify email delivery.
6. Rehearse a restore: `deploy/restore.sh` against a real dump, then confirm the app
   comes back. Back up `FIELD_ENCRYPTION_KEYS` separately; a database dump without the
   key ring leaves every stored credential undecryptable.
7. Personally onboard a small pilot group and observe their first successful workflow before widening access.

This increment does not establish production deployment, provider approval or live-provider acceptance.
