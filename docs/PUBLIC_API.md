# Public API and outbound webhooks

The public API lets agencies, Zapier, n8n and Make plug Instantlify into their own stack. It is workspace-scoped: an API key belongs to exactly one workspace and can never read another.

## Authentication

Create a key under **Integrations → API keys** (workspace owner only). The raw key is shown once and stored as a SHA-256 hash. Send it on every request:

```
X-API-Key: nmk_…
```

Keys carry scopes: `read` (GET) and/or `write` (PATCH/POST/DELETE). Requests are rate limited per key (`PUBLIC_API_RATE`, default 600/min). Revoking a key also disables the webhook subscriptions it created.

## Endpoints

Base path: `/api/v1/`. Lists return `{results, next_cursor}`; pass `cursor` back to fetch older rows (`limit` ≤ 200).

| Method | Path | Notes |
| --- | --- | --- |
| GET | `me/` | Workspace, key scopes and event list (connector auth test) |
| GET | `leads/` | Filters: `stage`, `tag`, `email` |
| GET, PATCH | `leads/{id}/` | PATCH accepts `name`, `email`, `stage`, `tags`, `fields`, `opted_out`; emits `lead.updated` |
| GET | `conversations/` | Filters: `lead`, `status` (`open`, `closed`, `needs_human`) |
| GET, POST | `conversations/{id}/messages/` | POST `{text, idempotency_key}` queues a reply through the normal delivery pipeline (opt-out and 24-hour window rules apply) → 202 |
| GET, POST | `webhooks/` | REST hooks: POST `{url, events}` → 201 with a one-time `secret` (HMAC) and `token` (shared header) |
| DELETE | `webhooks/{id}/` | Unsubscribe |
| GET | `webhooks/sample/{event}/` | Sample payload for connector "perform list" steps |

## Outbound webhooks

Events: `lead.created`, `lead.updated`, `lead.hot`, `message.received`, `message.sent`, `conversation.handoff`, `call.booked`, `payment.paid`.

Deliveries are `POST` requests with a JSON body:

```json
{"event": "lead.hot", "workspace_id": "…", "occurred_at": "…", "data": {…}}
```

Headers: `X-Instantlify-Event`, `X-Instantlify-Delivery` (unique ID, use it to dedupe), `X-Instantlify-Signature: t=<unix seconds>,v1=<hex>` where `v1 = HMAC-SHA256(secret, "<t>." + raw body)`, and `X-Instantlify-Token` (the subscription's shared token). Verify the signature and reject timestamps older than five minutes. Receivers that cannot compute an HMAC over the raw body (Make) should at least compare `X-Instantlify-Token` in constant time; it proves the sender holds the subscription's credential but does not protect against replay.

Only public HTTPS targets are accepted; private, loopback and link-local addresses are refused. Failed deliveries retry with exponential backoff up to 8 times; a subscription that fails 50 times in a row is disabled and must be re-enabled from the app.

## Connectors

Ready-made Zapier, n8n and Make packages live under `connectors/` in the repository; see `connectors/README.md` for install and publishing steps. They use only the endpoints above. Zapier and n8n verify the HMAC delivery signature; Make checks the shared `X-Instantlify-Token` header.
