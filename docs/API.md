# Application API

All tenant endpoints require an authenticated session or Bearer access token. Results are workspace-scoped and all API responses are `Cache-Control: no-store, private`. Lists use DRF pagination (`count`, `next`, `previous`, `results`), page size 50. Unknown/inaccessible tenant IDs return 404; an inadequate role within your tenant returns 403. The public, key-authenticated API is documented in `PUBLIC_API.md`.

## Identity

| Method | Path | Input / response |
| --- | --- | --- |
| GET | `/api/auth/csrf/` | CSRF cookie and `{csrfToken}` |
| POST | `/api/auth/signup/` | `{name, email, password}` → 201 user + session cookie |
| POST | `/api/auth/login/` | `{email, password}` → user + session cookie |
| POST | `/api/auth/logout/` | 204; invalidates session |
| GET | `/api/auth/me/` | `{id, name, email}` |
| POST | `/api/auth/token/` | `{email, password}` → `{access, refresh}` |
| POST | `/api/auth/token/refresh/` | `{refresh}` → rotated pair; previous refresh is blacklisted |
| POST | `/api/auth/token/revoke/` | `{refresh}` → revoke refresh; access expires within five minutes |

Browser clients first GET CSRF, then submit `X-CSRFToken` on every mutation with same-origin cookies. Authentication endpoints are throttled at 10/minute per IP.

## Workspace, team and white-label

Prefix: `/api/workspaces/`.

| Method | Path | Access |
| --- | --- | --- |
| GET, POST | `/api/workspaces/` | List own memberships (with effective `branding`); create `{name}` |
| GET, PATCH | `/{id}/` | Any member / owner+admin `{name}` |
| GET | `/{id}/members/` | Any member |
| PATCH, DELETE | `/{id}/members/{membership_id}/` | Owner changes roles; owner removes admins/agents, admin removes agents, anyone may leave |
| GET, POST | `/{id}/invitations/` | Owner/admin. `{email, role}` → one-time `accept_url`; pending invitations hold a seat |
| DELETE | `/{id}/invitations/{invitation_id}/` | Revoke |
| POST | `/api/invitations/accept/` | Signed-in invitee `{token}` |
| GET, PUT, DELETE | `/{id}/branding/` | Owner sets `brand_name`, `logo_url`, `primary_color`, `support_email`, `custom_domain`, `hide_platform_branding`; clients inherit their agency's branding |
| GET, POST | `/{id}/clients/` | Agency workspaces create/list client workspaces (`{name}`); the caller becomes the client's owner |
| GET | `/api/public/branding/` | Anonymous; branding for the request host (custom domains) |
| GET | `/{id}/audit/` | Owner/admin |
| GET | `/{id}/status/` | Dependency checks + pending jobs |
| GET, POST | `/{id}/data-operations/` | Owner; `{kind: export|delete, password, confirmation}` |
| GET | `/{id}/data-operations/{pk}/download/` | Export archive |

## Channels

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/{id}/connections/` | Never returns credentials |
| POST | `/{id}/meta/connect/` | Instagram OAuth start |
| GET | `/api/meta/callback/` | OAuth callback (plan channel limit enforced) |
| POST | `/{id}/channels/connect/` | `{provider: whatsapp|telegram|messenger, external_account_id, display_name, access_token}` (live mode) or `is_test` |
| POST | `/{id}/channels/{pk}/simulate/` | Local test inbound `{text, kind, sender_id}` |
| POST | `/{id}/channels/{pk}/disconnect/` | |
| GET | `/{id}/deliveries/` | Outbound delivery log |
| GET/POST | `/webhooks/instagram/`, `/webhooks/whatsapp/`, `/webhooks/messenger/` | Meta verification + signed events |
| POST | `/webhooks/telegram/{connection_id}/` | Secret-token verified |

## Automations, templates, experiments and analytics

| Method | Path | Notes |
| --- | --- | --- |
| GET, POST | `/{id}/automations/` | `{name, draft}` |
| GET, PATCH | `/{id}/automations/{pk}/` | Draft editing; `enabled` toggles a published flow |
| POST | `/{id}/automations/{pk}/publish/` | `{graph}` validated (node kinds, buttons, cycles, triggers) |
| GET | `/{id}/automations/{pk}/export/` | Portable JSON (`format: nemio.automation`) |
| POST | `/{id}/automations/import/` | `{template}` or multipart `file` → new draft |
| GET | `/{id}/automation-runs/` | Conversation states |
| GET | `/api/public/templates/?search=&category=` | Anonymous marketplace listing |
| GET | `/api/public/templates/{slug}/` | Template with graph |
| GET | `/{id}/templates/` | Templates this workspace published |
| POST | `/{id}/templates/publish/` | `{automation, title, description, category, price_cents}` |
| DELETE | `/{id}/templates/{pk}/` | Unlist |
| POST | `/{id}/templates/install/` | `{slug}` → new draft automation (free templates only) |
| GET, POST | `/{id}/experiments/` | `{name, control, variant, split, goal, auto_promote, min_leads}`; includes per-arm results |
| POST | `/{id}/experiments/{pk}/promote/` | `{winner: control|variant}`; a winning variant is republished under the control's ID |
| GET | `/{id}/analytics/funnel/?period=7d|30d|90d&automation=&provider=` | Distinct-lead funnel (comment → dm → triggered → replied → booked → paid), revenue, per-automation and per-channel breakdowns |

## Inbox and CRM

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/{id}/conversations/?search=` | Agents see unassigned + own |
| PATCH | `/{id}/conversations/{pk}/` | `assigned_to`, `status` (`open`, `closed`, `needs_human`), `ai_enabled` |
| GET, POST | `/{id}/conversations/{pk}/messages/` | POST `{text}` + `Idempotency-Key` |
| GET, POST | `/{id}/conversations/{pk}/notes/` | Internal notes |
| POST | `/{id}/conversations/{pk}/payment-link/` | `{offer}` + `Idempotency-Key`; sends a checkout link |
| GET | `/{id}/leads/` · GET, PATCH `/{id}/leads/{pk}/` | |
| POST | `/{id}/leads/{pk}/merge/` · `/{id}/leads/{pk}/sync/` | Merge duplicates; push to Airtable/Notion/GoHighLevel/Attio |
| GET, POST | `/{id}/integrations/` | `{provider, credentials, options, is_test}`; providers: google_calendar, calcom, airtable, notion, gohighlevel, attio, slack, elevenlabs, stripe. Responses carry `status` (`active`, `reconnect_required`, `disconnected`); saving credentials resets it to `active` |
| POST | `/{id}/integrations/{provider}/oauth/` | Owner/admin; `google_calendar` or `slack` → `{authorization_url, mode}`. 503 until the provider app is configured (local fake mode returns a test callback) |
| GET | `/api/integrations/callback/{provider}/` | Browser return from the provider; user-bound single-use state, then redirects to `/w/{id}/integrations?integration=connected\|test-connected\|cancelled\|failed` |
| DELETE | `/{id}/integrations/{pk}/` | Owner/admin; revokes the grant remotely when possible, clears credentials, keeps job history; → `status: disconnected` |
| WS | `/ws/workspaces/{id}/` | Session-authenticated; sends `{"type":"refresh"}` hints |

## AI agent

The agent config carries `mode`: `agent` (default; LangGraph sales agent with triage, stages and guarded tools) or `simple` (one grounded model call per message, no tools; handoff keywords, the plan cap and opt-out rules still apply).

| Method | Path | Notes |
| --- | --- | --- |
| GET, PUT | `/{id}/agent/` | Prompt, provider/model/key, tools, `qualifying_fields`, `triage_enabled`, `handoff_keywords`, `max_tool_rounds`, token prices |
| GET, POST | `/{id}/documents/` · DELETE `/{id}/documents/{pk}/` | Knowledge upload (PDF/TXT/MD ≤ 2 MB or text) |
| GET | `/{id}/agent-audit/` | Runs, tool calls (input/output), usage |

## Payments, billing and content

Plan gating: an action outside the workspace's plan returns **402** with `{detail, code: "plan_limit_exceeded", upgrade_required: <limit name>}`. Limit names: `max_instagram_accounts`, `max_contacts`, `team_seats`, `max_ai_messages`, `ai_agent_enabled`, `integrations_unlocked`, `content_scheduling_enabled`, `voice_notes_enabled`. `GET /{id}/billing/` returns `limits` (null = unlimited) and `catalog` (active public tiers with monthly/annual prices). Checkout takes `{kind: checkout, plan, interval: monthly|annual}`; a workspace's first subscription gets `STRIPE_TRIAL_DAYS` (default 7) of trial on any interval. `GET /api/public/plans/` is the anonymous catalog for the pricing page. `GET/PATCH /{id}/billing/credits/` returns the prepaid AI balance (cents, sub-cent precision), auto top-up settings and the last 50 ledger rows; `POST /{id}/billing/` with `{kind: credits, amount_cents}` starts a top-up checkout that also saves the card for auto top-ups. Connections carry `locked` when a downgrade left the workspace over its account limit: locked accounts keep receiving and replying but cannot be used for new posts or simulation until the workspace is within its limit again.

| Method | Path | Notes |
| --- | --- | --- |
| GET, POST | `/{id}/offers/` · GET, PATCH `/{id}/offers/{pk}/` | In-chat offers (amount ≥ 0.50) |
| GET | `/{id}/payments/` | Checkouts and their status |
| POST | `/webhooks/stripe/{workspace_id}/` | Tenant Stripe webhook (`checkout.session.completed`) verified with the workspace's own webhook secret |
| GET, POST | `/{id}/billing/` · GET `/{id}/billing/jobs/{job}/` | Platform subscription (checkout/portal jobs) |
| POST | `/webhooks/stripe/` | Platform Stripe webhook |
| GET, POST | `/{id}/posts/` · GET, PATCH, DELETE `/{id}/posts/{pk}/` | Content calendar (`connection`, `caption`, `media_url`, `media_type`, `scheduled_at`) |
| GET, PUT | `/{id}/bio/` | Link-in-bio page (`slug`, `title`, `bio`, `avatar_url`, `accent`, `links`, `published`) |
| GET, POST | `/api/public/bio/{slug}/` | Anonymous page data; POST `{index}` records a click and returns the URL |

## Public API management

| Method | Path | Notes |
| --- | --- | --- |
| GET, POST | `/{id}/api-keys/` · DELETE `/{id}/api-keys/{pk}/` | Owner creates (`{name, scopes}`; raw key returned once) and revokes |
| GET, POST | `/{id}/webhooks/` · DELETE `/{id}/webhooks/{pk}/` | Subscriptions (`{url, events}`) |
| GET | `/{id}/webhook-deliveries/` | Delivery log |

## Health

`GET /health/live/` checks process liveness. `GET /health/ready/` returns 200 only when PostgreSQL, Redis and a recent Beat→worker heartbeat are present; otherwise 503.


## Growth surfaces (platform-owned)

Written from the tenant app and the public marketing site; read only by the console.
Anonymous endpoints are write-only and return nothing readable.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/growth/funnel/` | Session/JWT | Wizard or tour step `{flow, step, status, workspace_id?}`; unknown steps are 400 |
| GET | `/api/growth/wizard/` | Session/JWT | Resume point `{step, completed, finished, steps}` |
| POST | `/api/growth/visit/` | Anonymous | Marketing page visit `{page, source?, referrer?}` → 204 |
| POST | `/api/growth/blog-view/` | Anonymous | Blog beacon `{slug, scroll_depth_pct, time_spent_seconds}` → 204 |
| POST | `/api/growth/tickets/` | Optional | Open a support ticket `{subject, email, category, body?, name?}` |
| POST | `/api/growth/support-chat/` | Anonymous | One support-assistant turn; the reply may be a `[[REQUEST_NAME_CARD]]` / `[[REQUEST_EMAIL_CARD]]` sentinel. `create_ticket: true` opens a ticket and refuses without name and email |
| GET | `/api/growth/announcements/?page=&workspace_id=` | Session/JWT | Active strips and unseen popups for this viewer |
| POST | `/api/growth/announcements/<id>/seen/` | Session/JWT | Mark a popup seen |
| GET / POST | `/api/growth/promo/` | Session/JWT | Live campaign for a workspace (GET records `shown`); POST `{workspace_id, slug}` records `claimed` |
| GET | `/api/blog/`, `/api/blog/<slug>/` | Anonymous | Published posts only |

Console endpoints live under `/ops/` on the admin host, are POST-only, role-checked and
audited: users (`ban`, `unban`, `email`, `portal-link`, `create`), AI credits
(`credits/test`, `credits/rates`), automations (`copy`, `transfer`), blog (posts and
categories), tickets, knowledge base, promos, notices, email templates, segments and
`billing-scan`.
