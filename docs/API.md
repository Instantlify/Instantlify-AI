# Phase 0 API

All tenant endpoints require an authenticated session or Bearer access token. Results are workspace-scoped and all API responses are `Cache-Control: no-store, private`. Lists use DRF pagination (`count`, `next`, `previous`, `results`), page size 50.

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

Browser clients first GET CSRF, then submit `X-CSRFToken` on every mutation with same-origin cookies. Login rotates CSRF, so fetch it again before the next mutation. API clients use `Authorization: Bearer <access>`; they do not store tokens in a browser. Authentication endpoints are throttled at 10/minute per IP using Redis. Generic anonymous API requests are 60/minute; authenticated requests are 300/minute per user. An edge limiter is still required for a public deployment.

## Workspace and roles

Prefix: `/api/workspaces/`.

| Method | Path | Access |
| --- | --- | --- |
| GET, POST | `/api/workspaces/` | List own memberships; create `{name}` with caller as owner |
| GET | `/{workspace_id}/` | Any member |
| PATCH | `/{workspace_id}/` | Owner/admin; `{name}` |
| GET | `/{workspace_id}/members/` | Any member |
| PATCH | `/{workspace_id}/members/{membership_id}/` | Owner only; `{role: "admin" | "agent"}`; cannot mutate owner |
| DELETE | `/{workspace_id}/members/{membership_id}/` | Owner removes admins/agents; admin removes agents; any non-owner may leave. Their assigned conversations are unassigned |
| GET, POST | `/{workspace_id}/invitations/` | Owner/admin. POST `{email, role}` (admins may invite agents only) → 201 with a one-time `accept_url`. Pending invitations count toward the plan's `seat_limit` |
| DELETE | `/{workspace_id}/invitations/{invitation_id}/` | Owner/admin; admin invitations can be revoked by the owner only |
| POST | `/api/invitations/accept/` | Signed-in invitee `{token}`; email must match; single-use, 7-day expiry, seat limit rechecked |
| GET | `/{workspace_id}/audit/` | Owner/admin, newest first |
| GET | `/{workspace_id}/status/` | Any member; dependency checks + pending setup jobs |
| GET | `/{workspace_id}/connections/` | Any member; never returns credentials |
| POST | `/{workspace_id}/meta/connect/` | Owner/admin; returns local OAuth URL only when fake mode is enabled |
| GET | `/api/meta/callback/?state=…&code=…` | Same user/session; consumes unexpired single-use state |

Unknown/inaccessible tenant IDs return 404. Inadequate role within your tenant returns 403. Ownership transfer is intentionally absent. Invitation emails are not sent yet; the inviter shares the returned link.

## Health

`GET /health/live/` checks process liveness. `GET /health/ready/` returns 200 only when PostgreSQL, Redis and a recent Beat→worker heartbeat are present; otherwise 503. Health endpoints expose no tenant data. They are infrastructure endpoints and should be restricted at public ingress.
