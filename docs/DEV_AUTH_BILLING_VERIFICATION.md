# Development authentication and billing verification

Changes are delivered through feature branches into dev. Main remains the production branch.

## Stripe sandbox

Plans are published as the Stripe products instantlify-starter, instantlify-pro and instantlify-scale, displayed as Instantlify Starter, Instantlify Pro and Instantlify Scale. Never replace price IDs or recreate subscriptions to fix branding. The publish_plans command now also updates the display name of existing products. Its dry run reports proposed renames without applying them.

Stripe's internal Account name is separate from its public business name. In the sandbox used by dev, set Business details / Public details / Public business name to Instantlify. Check any receipt and invoice statement descriptors for legacy text as well. Stripe requires its Dashboard to update your own account: https://docs.stripe.com/api/accounts/update

The sandbox product names were updated in place during investigation. All existing price IDs, amounts, currencies and recurring settings were compared before and after and were unchanged. The portal configuration contains no legacy business-profile text. Existing invoices still carry the old account name; finalized historical billing documents were not rewritten. The public business name needs to be corrected before verifying fresh Checkout authorization text, portal pages, invoice previews and receipt emails.

## Magic-link delivery

Deploy the web/backend and Celery worker from the same revision. The worker must register apps.tenants.tasks.deliver_magic_link. Both need the correct SMTP settings, DEFAULT_FROM_EMAIL and PUBLIC_APP_URL=https://dev.instantlify.com. Ensure Redis and the worker are healthy. A console/dummy backend now returns an unavailable response rather than claiming a link will arrive.

Requests enqueue delivery; transient SMTP failures retry three times with 30/60/120 second delays. The API retains a generic response for registered, unknown and ineligible accounts, with a 60-second per-address resend guard in Redis and the existing per-IP auth throttle. Only a user ID enters the task payload; tokens and email addresses are excluded from application delivery logs.

Search backend/worker logs for magic_link_queue_failed, magic_link_backend_unavailable, magic_link_delivery_failed and magic_link_delivery_accepted. Accepted means the email backend accepted the message, not that the recipient's inbox delivered it. Correlate the QA request window with SMTP/provider delivery, bounce and suppression logs. The exact failed recipient and deployed provider logs were unavailable during this investigation; local SMTP TLS and authentication succeeded without sending a message.

After deployment, QA should request a link for a known registered account, check inbox/spam, redeem it once, and confirm a second redemption fails. A separate token must fail after 15 minutes. An unknown account must receive the same public response without an email. Check that repeated requests during the cooldown do not enqueue another delivery, and that a request after the cooldown does.

## Registration

Password registration creates an account and sends verification mail without establishing a login session. The UI returns to Sign in with a success message, removes mode=signup and preserves selected plan, interval and invitation/consent parameters. First sign-in continues through onboarding; completed accounts return to their workspace dashboard. Google sign-in and magic-link authentication keep their existing sign-in behavior.
