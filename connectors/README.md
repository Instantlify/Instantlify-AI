# Connectors

Packages that plug Nemio into Zapier, n8n and Make. All three sit on the public API (`docs/PUBLIC_API.md`): a workspace API key sent as `X-API-Key`, REST-hook subscriptions on `/api/v1/webhooks/`, and signed outbound deliveries. Nothing here has privileged access; anything a connector can do, the key it holds could do with `curl`.

Every connector needs two inputs: the **Nemio URL** of your deployment and an **API key** from Integrations → API keys. Instant triggers need the `write` scope so the connector can create and delete its subscription; the connection test calls `GET /api/v1/me/`.

| Connector | Path | Triggers | Actions | Signature check |
| --- | --- | --- | --- | --- |
| Zapier (Platform CLI) | `connectors/zapier` | One REST-hook trigger per event | Send message, update lead, find lead | HMAC verified in `perform`, 5-minute tolerance |
| n8n (community node) | `connectors/n8n` | `Nemio Trigger` (multi-event) | Lead get/list/update, conversation list, message list/send | HMAC verified with the stored secret; 401 otherwise |
| Make (custom app) | `connectors/make` | `Watch Events` instant trigger | Send message, update lead, search leads | Shared `X-Nemio-Token` compared to the value saved at attach; requests without it get 401 |

## Zapier

```sh
cd connectors/zapier
npm install
npm test             # unit tests with mocked HTTP
npx zapier login     # once
npx zapier register "Nemio"   # first time only; writes .zapierapprc
npx zapier push
```

Invite testers with `zapier users:add`. Publishing to the public directory goes through Zapier's review; the app already satisfies the REST-hook requirements (subscribe, unsubscribe, `performList` samples).

## n8n

```sh
cd connectors/n8n
npm install
npm run build        # dist/ with compiled nodes and the icon
```

Install into an n8n instance from the built package (`npm pack`, then Settings → Community nodes, or set `N8N_CUSTOM_EXTENSIONS` to the package directory for self-hosted). Publish with `npm publish` under the `n8n-nodes-nemio` name to make it installable by name. The trigger stores the subscription ID and secret in the node's static data; rotating the API key invalidates the subscription, and the trigger recreates it on the next activation.

## Make

Import the JSON files into a custom app in Make's developer platform (or the "Make Apps" VS Code extension): `base.json` → Base, `connections/nemio.json` → a new API-key connection, `webhooks/nemio.json` → a new webhook, and each file under `modules/` → a module of the type it declares. The `Watch Events` module attaches the webhook on scenario activation and detaches it on deactivation.

Make cannot recompute an HMAC over the raw request body, so the Make webhook uses the second credential every subscription gets: a shared `X-Nemio-Token` header. The token is stored at attach time and every delivery whose header does not match is answered with 401 before any scenario runs. This proves the sender holds the subscription's token over TLS; it does not give the replay window or body-integrity guarantees of the HMAC signature that Zapier and n8n check. Dedupe on `delivery_id` if a scenario must be idempotent.

## Payload shape

Deliveries are `{event, workspace_id, occurred_at, data}`. Zapier flattens `data` into the record and keeps the delivery ID as `id` (the record's own ID becomes `resource_id`); n8n does the same with `delivery_id`; Make exposes `data` as a collection.

## Releasing

`connectors/scripts/publish.py` runs the same checks locally and in CI (`.github/workflows/connectors.yml`):

```sh
python connectors/scripts/publish.py check                       # tests, zapier validate, n8n build + npm pack, Make schema
python connectors/scripts/publish.py n8n --version 1.1.0 --publish    # needs NPM_TOKEN
python connectors/scripts/publish.py zapier --version 1.1.0 --push    # needs ZAPIER_DEPLOY_KEY and .zapierapprc
python connectors/scripts/publish.py make                        # writes connectors/dist/nemio-make-app.zip
```

Without `--publish` / `--push` nothing leaves the machine. Pushing a tag `connectors-vX.Y.Z` runs the release job: n8n goes to npm, Zapier gets a new *private* version, and the Make bundle is attached to the GitHub release. Three steps stay manual on purpose:

- **Zapier**: run `zapier register "Nemio"` once and commit `.zapierapprc`; after each push, `zapier promote X.Y.Z` moves users over. The public App Directory listing goes through Zapier's review.
- **n8n**: the npm package installs by name immediately; the "verified" badge is n8n's own review.
- **Make**: there is no publishing CLI. Upload the bundle in Make's developer platform, then request review for public listing.

The release job runs in the `connectors-release` GitHub environment, which holds `NPM_TOKEN` and `ZAPIER_DEPLOY_KEY`; add required reviewers there so a tag alone cannot publish.
