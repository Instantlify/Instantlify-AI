# WhatsApp connection and local verification

Nemio uses Meta's WhatsApp Cloud API. Clients connect from **Integrations → Channels → Connect WhatsApp**. Meta handles business selection, number selection, and ownership verification. Nemio exchanges the authorization code on the backend, checks the app, granted permissions, shared business account, and selected number, then stores the token encrypted.

After authorization, clients finish number registration with their six-digit WhatsApp security PIN. An already registered number can skip registration only after Meta confirms that it is connected. Registration and notification subscription are separate checkpoints, so a failed subscription can be retried without resetting the PIN. Interrupted setup appears as **Finish WhatsApp setup** on the channel card. Existing connections can be reauthorized with **Reconnect WhatsApp**, including when the account limit has already been reached.

## Configure your local environment

Add these values to the ignored root `.env`; never commit credentials:

```dotenv
CHANNEL_ADAPTER_MODE=live
META_APP_ID=<your Meta app ID>
META_APP_SECRET=<your Meta app secret>
WHATSAPP_APP_SECRET=<same secret when WhatsApp uses that Meta app>
WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID=<Facebook Login for Business signup configuration ID>
META_WEBHOOK_VERIFY_TOKEN=<a random verification value you choose>
PUBLIC_APP_URL=https://<your public HTTPS frontend tunnel host>
```

Use a Meta app configured for WhatsApp and a Facebook Login for Business configuration using WhatsApp Embedded Signup with a code response. Configure `whatsapp_business_management` and `whatsapp_business_messaging`. App administrators/testers may test in development; onboarding external businesses requires Meta's applicable business verification, app review, advanced permissions, and published app configuration. Meta approval cannot be completed by adding keys to Nemio.

Expose the frontend on local port **3000** through a public HTTPS tunnel using your preferred tunneling tool. The frontend now forwards `/webhooks/` to the backend, so the same public origin serves the portal, authenticated API, and signed WhatsApp callbacks. Keep the frontend's `BACKEND_INTERNAL_URL` pointing to `http://backend:8000` in Docker. There is no need to expose the backend port separately for this setup.

Add the tunnel hostname to `ALLOWED_HOSTS` and the full HTTPS origin to `CSRF_TRUSTED_ORIGINS` in `.env`, retaining the existing local values. Add the HTTPS origin/domain to the Meta app's allowed JavaScript SDK domains, app domains, and the applicable OAuth redirect allowlist. Open Nemio through the HTTPS tunnel for the connection test, sign in there, and use that same origin throughout setup. If the tunnel URL changes, update all of these settings together.

In the WhatsApp product settings in Meta:

1. Set the callback address to `https://<tunnel host>/webhooks/whatsapp/`.
2. Set the verification token to the exact `META_WEBHOOK_VERIFY_TOKEN` you chose.
3. Verify the callback and subscribe to the **messages** field. The connection flow subscribes Nemio's app to the selected WhatsApp Business Account as well; both app-level callback setup and account subscription are needed.
4. Confirm that the number and business can use Cloud API and have the necessary Meta billing setup. Test numbers have Meta restrictions on allowed recipients.

Apply environment changes to the local services:

```powershell
docker compose up -d --no-deps --no-build backend worker beat
```

If starting from a fresh checkout, build and migrate first using the normal project setup. The delivery receipt fields are added by migration `channels.0006_delivery_provider_receipts`.

## Test your own Meta account before configuring Embedded Signup

Embedded Signup is the client onboarding option. For an initial developer test with your **own** WhatsApp account, **Advanced: manual credentials and test channels** also accepts a **WhatsApp business account ID**. This path does not require an Embedded Signup configuration ID.

Create your Meta developer app, enable WhatsApp, and open its API setup. Meta provides a test business account/number; add and verify your own phone as a permitted test recipient. Configure the app secret, webhook verification token, and public HTTPS callback as above. In Nemio's advanced channel form, select WhatsApp and enter the **phone number ID**, **WhatsApp business account ID**, display name, and access token from that API setup. Leave the local-test checkbox **off**, because these are real Meta API calls. Nemio verifies that the phone belongs to that business, subscribes to notifications, and exposes approved templates for that account. If Meta indicates that registration is still needed, the channel offers **Finish WhatsApp setup**.

After token expiry, submit the same phone number and business account with a fresh token in the advanced form. Nemio updates the existing connection and keeps its contacts and conversation history. When testing ordinary replies, send an inbound message from the allowed recipient first to open the customer-service window.

If your eventual production number is already used in the WhatsApp Business mobile app, check Meta's coexistence eligibility and onboarding requirements before registering it for Cloud API. This implementation does not automatically migrate or disconnect an existing mobile-app number.

## Messages and approved templates

New incoming customer messages create or update a contact and appear in the inbox. AI, automations, and team replies use the same conversation. Old WhatsApp app history is not imported by this Cloud API connection flow. Migration/coexistence history sync and WhatsApp calling are separate provider capabilities, not included in this connection.

Regular replies remain subject to the 24-hour customer-service window. Outside that window, use **Send approved message** in a WhatsApp conversation:

1. Load the approved templates belonging to that connection's business account.
2. Choose the message and language, fill its required details, and review the preview.
3. Confirm that the customer has agreed to receive those WhatsApp messages.
4. Send. Meta messaging charges may apply.

Supported inbox formats are text templates with positional or named text variables, optional text/image/video/document headers, static phone/website/quick-reply buttons, and dynamic website buttons. Files must use public HTTPS links. Special formats such as carousels, location headers, commerce buttons, and authentication-code templates are explicitly unavailable in this composer. Create/manage template approvals in **WhatsApp Manager**; Nemio reads the approved catalog rather than manufacturing an approval.

The backend checks the exact approved definition when queuing and again before sending. Paused, removed, changed, or unapproved templates are not sent. Customer opt-outs, platform controls, connection expiry, and delivery rate limits remain enforced. Sending a template does **not** reopen ordinary replies: a new customer response does that. Repeated submissions with the same request key return the same queued delivery. Uncertain provider delivery is marked `unknown` rather than automatically sent twice.

Signed sent/delivered/read/failed receipts update message progress in the inbox. Duplicate and out-of-order receipts do not create customer messages or move read receipts backward. A provider's acceptance is distinct from confirmed delivery/read status.

## Live acceptance checklist

Run only with your own authorized test number/recipient:

- Connect through Meta, finish registration/subscription, and confirm the channel becomes active.
- Send a message from the test recipient to the business number. Confirm one contact/thread and one inbound message, even if Meta retries its webhook.
- Send a human reply, then test an enabled automation and AI reply within the open window. Confirm delivery on the actual phone and the corresponding receipt in Nemio.
- Take over as a teammate and confirm the AI stops replying for that conversation.
- Use a conversation with an expired window: ordinary replies must stay disabled; an approved template with confirmed consent may queue and send. A customer reply must reopen ordinary replies.
- Confirm an opted-out contact cannot be messaged, including through templates.
- Disconnect/reconnect and repeat a message without duplicating the contact/thread.

No live WhatsApp messages were sent while implementing this feature. At implementation time, this local environment had no Meta app credentials, signup configuration, public HTTPS address, or live WhatsApp connection. Automated tests use provider doubles; real account permissions, Meta app review, callback reachability, and recipient delivery still require the live acceptance checks above.

## Primary references

- [Meta's Embedded Signup reference app](https://github.com/fbsamples/business-messaging-sample-tech-provider-app)
- [Meta's Embedded Signup API collection](https://www.postman.com/meta/whatsapp-business-platform/documentation/du6gzjv/embedded-signup)
- [Meta's phone registration API](https://www.postman.com/meta/whatsapp-business-platform/request/zb2u18b/register-phone)
- [Meta's template sending API](https://www.postman.com/meta/whatsapp-business-platform/request/lwtlz1k/send-message-template-interactive)
- [WhatsApp Business Messaging Policy](https://whatsappbusiness.com/policy/)
