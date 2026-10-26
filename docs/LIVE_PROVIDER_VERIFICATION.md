# Live provider verification

Automated regressions use provider fakes and bounded HTTP mocks. They establish application
behavior but do not prove a customer's provider permissions, delivery or billing callbacks.
The following checks require owner-supplied sandbox accounts and an agreed test recipient.
No real customer messages or charges have been sent during implementation.

Stripe connection status was checked read-only against Stripe's API: subscription billing
credentials work in test mode and a signing secret is configured. The enabled registered
destination is on nemio.ai at a different path from this build's /webhooks/stripe/ route.
The local database has received zero BillingEvent callbacks. A destination returning HTTP 200
to GET does not establish signature verification or correct workspace reconciliation. Awaiting
the user's choice of a local Stripe forwarder or deployed backend for the next test.

| Check | Required setup | Evidence of success |
| --- | --- | --- |
| Knowledge refresh | A test Sheet, Airtable table, Notion page or Shopify store connected in Nemio | Enable a schedule, change one test answer, observe one document revision and successful indexing; unchanged refresh does not produce another embedding charge. |
| Custom call agent | Test Vapi or Retell account with an available model and voice | Create an agent in Nemio; provider dashboard contains the matching agent/response-engine IDs. No phone call is needed for this check. |
| Calling | Provider-owned caller number, user-approved test recipient and an explicit private call request | One accepted call, final provider outcome reconciled once, continuation receives the bounded outcome; no duplicate call after a worker retry. |
| ZorroMail | Transactional test API key, verified sender domain and user-approved recipient | Form confirmation creates one provider message. Confirm actual delivery in the provider dashboard or recipient inbox; a duplicate form request does not create another message. |
| Creator followers | A real connected Instagram business account selected in a test creator kit | Source refresh timestamp advances and public follower count matches the authorized provider response. Disconnecting removes the account from public metrics. |
| Form webhook | Controlled test receiver subscribed to form.submitted | One signed event per unique form request; no provider keys or internal operational fields in its public form definition. |
| Billing callbacks | Billing provider test mode, test checkout and a reachable test webhook endpoint | Verify the provider-signed callback updates the intended workspace plan, period and status; duplicate callbacks do not create duplicate effects. Check cancellation/downgrade and failed-payment transitions. |

Configure secrets through Nemio or its deployment settings, never in chat, screenshots,
fixtures or this document. A local stub checkout is not evidence of a live provider callback.

Notavo and Poppy still require the correct service identity and official endpoint/authentication
specifications. Their catalogue entries remain unavailable until an implementation can be
checked against those contracts; no guessed endpoints are used.
