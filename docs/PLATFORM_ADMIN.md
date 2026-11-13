# Internal platform console

The console is served by Django at **http://ops.localhost:8000/ops/** in local Compose. It is deliberately absent from the customer navigation and returns 404 on the customer host. Production requires a distinct `PLATFORM_ADMIN_HOST`; it cannot equal the customer `PUBLIC_APP_URL` hostname.

## First owner and login

1. Create an ordinary account with a strong password through the existing signup flow, or use Django `createsuperuser` interactively. Do not put passwords in shell arguments.
2. Grant the first platform owner from the server:

   ```sh
   docker compose exec backend python manage.py bootstrap_platform_owner YOUR_USERNAME
   ```

3. Open the internal console, sign in with that username/password, and add the displayed setup key to a TOTP authenticator (SHA1, six digits, 30-second period). Confirm one code. No dashboard or operational action is available before enrollment and verification.

There is no default administrator password and no automatically privileged tenant owner. `is_staff` or `is_superuser` alone does not grant console access. Subsequent staff receive email-bound, single-use invitations created by a platform owner. Tokens are displayed once for private delivery, expire in 24 hours, and can be revoked. Invitees must already have an account and verify its password; accepting an invitation does not skip MFA.

## Roles

| Capability | Owner | Support | Analyst |
| --- | --- | --- | --- |
| Aggregate metrics, tenant listing, operational status, audit | Yes | Yes | Yes |
| Time-limited read-only customer support view | Yes | Yes | No |
| Suspend/reinstate one workspace; tenant feature pauses | Yes | Yes | No |
| Global kill switches | Yes | No | No |
| Staff invitations, revocation, role changes | Yes | No | No |
| Record provider review/permission/certificate status | Yes | No | No |

MFA proofs expire after 30 minutes. Enrollment requires password verification within 10 minutes. Used TOTP counters cannot be replayed; five failed codes lock verification for 15 minutes. Login/invitation password attempts are throttled by account and client IP. Changing a role invalidates its existing MFA proofs. Revocation and user deactivation are checked on every request; the last active platform owner cannot be removed through the console.

Lost authenticator recovery is a server-only, audited operation:

```sh
docker compose exec backend python manage.py reset_platform_mfa USERNAME --reason "Verified recovery ticket reference"
```

This invalidates proofs and the previous secret; the user must verify their password and enroll again. Protect host/management-command access as privileged infrastructure access.

## Support access

View-as is an explicit **read-only support view**, not a replacement of the operator's identity with a customer's session. It displays the workspace's recent conversations/messages under a persistent warning banner, requires a reason, expires after ten minutes and is bound to its creating operator. Starting, reading and ending it are audited. Expired or revoked sessions cannot retrieve another page; content already read cannot be recalled. It cannot send messages, change customer settings or perform refunds.

## Pause semantics

- `workspace`: suspend tenant API access, API-key access, websocket refresh access and business workers. Provider ingress continues to verify and durably store messages, so suspension does not discard customer webhooks.
- `ai`: pause agent generation, knowledge ingestion, transcription, segmentation and queued AI replies.
- `messaging`: pause inbound processing and outbound delivery.
- `automations`: pause flow execution and queued flow deliveries.
- `automation:<UUID>` with a workspace scope: pause one flow and its queued deliveries.
- `content`: pause scheduled publication.
- `integration:<provider>`: pause the corresponding provider operations. Provider names are restricted to the console's allowlist.

Global pauses override local resumes. Workers check database controls before claiming work, and provider boundaries check relevant controls again. Pending work remains pending. Requests already in flight cannot be recalled; interrupted/ambiguous side effects still require review under the existing delivery safeguards. On resume, queued replies are rechecked against opt-out and messaging-window rules. Billing reconciliation and retention continue while a tenant is suspended.

## Metrics and operational status

- Last-30-day tenant/aggregate message and recorded model usage/spend; searchable, paginated tenant list, spend/usage sorting.
- Meta request/error counters and authenticated webhook acceptance/signature-failure counters start at installation. Meta request counters include failed attempts. Per-workspace Meta counts are attributed by worker/OAuth context. Calls outside that context remain visible in the aggregate.
- Live shared Redis bucket usage/TTL and configured ceiling; no ceiling and unavailable Redis are explicitly distinguished from zero usage.
- Delivery status counts, queue backlog, account token expiry/status, and operator-verified Meta review/permission/mTLS certificate expiry records. These records do not configure Meta and are not an automated claim of approval. mTLS expiry is applicable only when your ingress uses it.
- Hourly Stripe subscription snapshots yield gross contracted MRR by currency, excluding metered usage, discounts and tax. Annual/weekly/daily prices are normalized. Unsupported tiered price structures are reported as sync failures, not fabricated revenue. Do not sum currencies without conversion.
- Thirty-day customer churn needs a snapshot baseline from 30 days earlier. It remains unavailable until that history exists. Overage trends are daily snapshots of generation usage above allowance, not invoice totals. Recorded model spend depends on configured pricing and is not an invoice reconciliation.

## Production deployment

Set `PLATFORM_ADMIN_HOST=ops.example.com` and route only that hostname's `/ops/` to Django. Keep the backend inaccessible directly from the public internet. Use HTTPS, host-only cookies (the default), and a trusted reverse proxy that overwrites forwarding headers. Do not route `/ops/` through the customer Next.js host. An edge VPN/IP restriction is recommended; `PLATFORM_ADMIN_NETWORKS` optionally validates `REMOTE_ADDR` CIDRs and deliberately ignores spoofable forwarded IP headers. Behind a proxy, apply the real client allowlist at the edge.

The console uses CSRF protection, no-store responses, no-referrer, CSP and frame restrictions. No channel/LLM/Stripe credential is rendered. MFA setup material appears only before confirmation. Logs use the application's existing closed-schema formatter.

Audit entries are insert-only at the model layer and protected against UPDATE/DELETE by PostgreSQL/SQLite triggers. Workspace IDs and actor IDs are retained as strings so deleting a tenant does not delete platform history. In production, use a separate migration owner and grant the runtime database role SELECT/INSERT only on `platform_ops_platformaudit`, with no UPDATE, DELETE, TRUNCATE, schema/trigger alteration or superuser rights. A database administrator can override database controls; maintain independently retained backups/log exports for that threat model. Never use the development database superuser as the production runtime role.

## Verification

`backend/tests/test_platform_ops.py` covers host isolation, tenant/superuser denial, mandatory enrollment, RFC TOTP vector/replay/encryption/lockout, role restrictions, session revocation, last-owner protection, database audit immutability, invitation binding, support expiry, CSRF, IP spoofing, login throttling, paused-worker behavior and revenue normalization. Run the complete backend suite in Compose to include PostgreSQL and Redis checks.

Real Stripe data, provider review status, corporate DNS/TLS/VPN and staff enrollment must be configured by the operator. Local tests establish implementation behavior, not those external production conditions.


## Website chat and client support tickets

The public site and authenticated portal have a floating support launcher. Visitors can ask Instantlify questions or submit a categorized ticket with a name, email, subject and description. Logged-in clients can also open **Help & support** in the sidebar to create tickets, see their status and read or send replies. Replying to a resolved ticket reopens it. Chat-created client tickets include the recent conversation.

Apply the normal backend migrations before deploying this version (`python manage.py migrate`); migration `platform_ops.0008` adds a reporter relationship and reply messages. Existing tickets remain in the admin queues. They are not automatically linked by email to a client's account, so historical anonymous requests are not accidentally exposed.

The authenticated API is `/api/workspaces/<workspace_id>/support/tickets/` (list/create) and `/api/workspaces/<workspace_id>/support/tickets/<ticket_id>/replies/` (reply). Both membership and ticket reporter ownership are required. The client list shows the latest 100 requests. Name and email are taken from the signed-in account, not trusted from the submitted JSON.

In the platform console's Support queues, expand **Conversation and reply** to read the original request and its thread, then send a response. Replies are saved to the ticket and emailed through the configured Django email backend. A mail failure is logged without losing the reply; clients can still read it in the portal. Assignment and resolution controls continue to work.

Production AI answers use `PLATFORM_OPENAI_API_KEY` and the platform knowledge base managed in the console. These are separate from customer agent keys, documents and credits. If the AI provider is unavailable, chat offers the ticket form instead. Real email delivery requires the existing mail provider configuration and `DEFAULT_FROM_EMAIL`; local/test delivery is not evidence of production email delivery.

## Scheduled announcements and client history

In **Notifications**, create or edit a strip or popup, enable it, and optionally set its start/end times and IANA time zone (default `Asia/Karachi`). Leave pages and tiers empty to reach every signed-in user. A blank start publishes immediately when enabled; a blank end has no expiry. The server enforces the schedule on each fetch, so no scheduler or worker configuration is needed. Visible client pages refresh automatically within 15 seconds under normal network conditions, without navigation or extending idle sessions.

The app bell combines announcement unread counts with existing assignment counts. Users can mark announcements read, explicitly acknowledge requested notices, and browse delivery history. Marking all read does not acknowledge notices. History retains delivered content after expiry, edits or deletion. Editing or re-enabling a notice creates a new revision for delivery; previous versions remain in history. Notices that expire before a user visits an eligible page are not delivered retroactively. Reads and acknowledgements are per user across their workspaces. Page and plan targeting still restrict initial delivery.

## Client device controls

**Settings → Profile → Devices and sessions** lists active browser sessions, their device/browser, IP address, last activity and expiry. A user can revoke an individual browser session or sign out everywhere, including the current browser. Existing sessions are backfilled during migration, with unavailable historical device details labelled accordingly. Sign out everywhere also invalidates issued API access/refresh tokens. Other open browser sessions detect revocation within 30 seconds while visible, or on their next authenticated request. Background checks do not renew the one-hour inactivity window.

Notavo, Poppy AI, Salesforce, HubSpot and Zapier remain labelled **Coming soon** in the integration catalogue and have no connect/configure action.

## Client AI model prices

The agent's model cards read the admin rate card's **Our rate** input/output values, per million tokens. **Real cost** is internal provider cost and is not the customer's selling price. The most specific model-ID pattern wins, using the same resolver as credit billing. If no specific pattern matches, the card explicitly identifies the admin fallback rate. Exact chat-model entries for supported OpenAI, Anthropic, Gemini and xAI model prefixes also appear in the catalogue; wildcard entries price models rather than creating model IDs. Reload the agent page after changing a rate. Decimal precision is retained, and a failed or empty catalogue response shows no hardcoded backup prices.
