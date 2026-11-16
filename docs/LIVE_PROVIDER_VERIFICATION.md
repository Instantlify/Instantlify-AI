# Live provider verification

Automated regressions use provider fakes and bounded HTTP mocks. They establish application
behavior but do not prove a customer's provider permissions, delivery or billing callbacks.
The following checks require owner-supplied sandbox accounts and an agreed test recipient.
No real customer messages or charges have been sent during implementation.

On 27 October 2026, WhatsApp Embedded Signup, number registration/subscription, own-account
API-setup connection, approved-template inbox sending and signed delivery/read receipts were
implemented. The final isolated PostgreSQL suite passed 711 tests and the production browser
WhatsApp/inbox/validation suite passed 26 checks; an additional own-account setup browser
check passed. These use provider doubles, not real Meta
accounts. Local inspection found no Meta app credentials, WhatsApp signup configuration,
public HTTPS app URL or live WhatsApp connection. The owner will configure Meta locally.
[WhatsApp local setup](WHATSAPP_LOCAL_SETUP.md) describes both the developer test-number path
and the client Embedded Signup path. Test inbound, human/AI/automation replies, receipts,
expired-window templates, opt-outs and reconnects with an authorized recipient before claiming
live acceptance. Special template formats, mobile-app history/coexistence migration and calls
are not implemented by this increment.

On 26 October 2026, the owner confirmed that everything runs locally and authorized Stripe
test-mode verification. Stripe CLI now forwards genuine, signed test events to the local
`/webhooks/stripe/` route; no deployed backend is required. Isolated ownerless workspaces
received subscription creation, update, plan change, plan restoration and cancellation callbacks.
The application mapped Starter → Pro → Starter, billing periods and trial/canceled states.
All fixture subscriptions were canceled; no existing subscription or workspace was modified.
No cards, real charges or customer email recipients were used.

Actual callbacks exposed a Stripe SDK object/dictionary compatibility error that mocked
responses had hidden. SDK responses are now converted recursively after signature validation
and at subscription/preview read boundaries. Zero-value invoices emitted during an ongoing
trial cannot prematurely activate it, including invoices created by trial plan changes.
Regression tests exercise the installed SDK's real signature parser, nested objects,
duplicate-event persistence and invoice ordering. Failed-payment, metered-charge, Connect and
tenant-checkout acceptance still need separate sandbox exercises; this is not full Stripe
production acceptance.

Final local evidence: 682 PostgreSQL tests passed; backend lint/format, Django system checks
and migration drift checks passed. The last real Stripe fixture received eight signed events,
all acknowledged with HTTP 200. Its paid zero-value trial invoices were ignored and all
subscription changes processed; the final account status is canceled.

## Repeat the local Stripe check

Install [Stripe CLI](https://docs.stripe.com/stripe-cli), and put the Stripe test secret key
in the ignored root `.env` as `STRIPE_SECRET_KEY`. Keep `PUBLIC_APP_URL` local. From the
repository root on Windows:

```powershell
.\backend\.venv\Scripts\python.exe tools/stripe_local.py
```

Keep that terminal running. The helper verifies test mode, captures the listener signing
secret without printing it, updates only `STRIPE_WEBHOOK_SECRET` in `.env`, and forwards to
`http://127.0.0.1:<INSTANTLIFY_BACKEND_PORT>/webhooks/stripe/` (default port 8000; this workstation
uses 8002). It logs only event IDs/types/statuses under ignored `.cache/stripe-local/`.
In another terminal, reload the backend environment and exercise isolated trial fixtures:

```powershell
docker compose up -d --no-deps --force-recreate backend
docker compose exec -T backend python manage.py verify_stripe_local --apply
```

The command requires a local app URL, a real test-mode balance response and a published
recurring test plan price. It switches to another configured test plan and back when one
exists, with proration disabled inside the trial. Its finalizer verifies ownership metadata
before canceling only its own subscription. Omitting `--apply` makes no provider calls or
writes. Canceled fixtures remain as audit records. Stop forwarding with Ctrl+C.
Local forwarding follows [Stripe's documented listener flow](https://docs.stripe.com/webhooks#local-listener);
the listener signing secret is distinct from a registered dashboard endpoint's secret.

| Check | Required setup | Evidence of success |
| --- | --- | --- |
| Knowledge refresh | A test Sheet, Airtable table, Notion page or Shopify store connected in Instantlify | Enable a schedule, change one test answer, observe one document revision and successful indexing; unchanged refresh does not produce another embedding charge. |
| Custom call agent | Test Vapi or Retell account with an available model and voice | Create an agent in Instantlify; provider dashboard contains the matching agent/response-engine IDs. No phone call is needed for this check. |
| Calling | Provider-owned caller number, user-approved test recipient and an explicit private call request | One accepted call, final provider outcome reconciled once, continuation receives the bounded outcome; no duplicate call after a worker retry. |
| ZorroMail | Transactional test API key, verified sender domain and user-approved recipient | Form confirmation creates one provider message. Confirm actual delivery in the provider dashboard or recipient inbox; a duplicate form request does not create another message. |
| Creator followers | A real connected Instagram business account selected in a test creator kit | Source refresh timestamp advances and public follower count matches the authorized provider response. Disconnecting removes the account from public metrics. |
| Form webhook | Controlled test receiver subscribed to form.submitted | One signed event per unique form request; no provider keys or internal operational fields in its public form definition. |
| Billing callbacks | Billing provider test mode, test checkout and a reachable test webhook endpoint | Verify the provider-signed callback updates the intended workspace plan, period and status; duplicate callbacks do not create duplicate effects. Check cancellation/downgrade and failed-payment transitions. |

Configure secrets through Instantlify or its deployment settings, never in chat, screenshots,
fixtures or this document. A local stub checkout is not evidence of a live provider callback.

Notavo and Poppy still require the correct service identity and official endpoint/authentication
specifications. Their catalogue entries remain unavailable until an implementation can be
checked against those contracts; no guessed endpoints are used.
