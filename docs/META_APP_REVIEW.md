# Meta App Review checklist

What Meta asks for, and where Instantlify provides it. Fill in the bracketed items before
submitting.

## URLs to enter in the Meta app dashboard

| Setting | Value |
|---|---|
| Privacy policy URL | `<PUBLIC_APP_URL>/privacy/` (draft: legal review and company details needed) |
| Terms of service URL | `<PUBLIC_APP_URL>/terms/` (draft: legal review and company details needed) |
| Data deletion callback URL | `<PUBLIC_APP_URL>/webhooks/meta/data-deletion/` |
| Deauthorize callback URL | `<PUBLIC_APP_URL>/webhooks/meta/deauthorize/` |
| Webhook callback (Instagram) | `<PUBLIC_APP_URL>/webhooks/instagram/` |
| Webhook callback (Messenger) | `<PUBLIC_APP_URL>/webhooks/messenger/` |
| Webhook callback (WhatsApp) | `<PUBLIC_APP_URL>/webhooks/whatsapp/` |
| OAuth redirect | `<PUBLIC_APP_URL>/api/meta/callback/` (check `META_REDIRECT_URI`) |

Both callbacks verify Meta's `signed_request` with `META_APP_SECRET`. Deauthorize
disconnects the person's Instagram/Messenger connections and deletes their tokens; data
deletion does the same and returns a confirmation code with a public status page at
`/data-deletion/?code=…`.

## Permissions and the use case to describe

| Permission | Why Instantlify needs it | What to show in the screencast |
|---|---|---|
| `instagram_business_basic` | Identify the connected professional account | Connecting an account in Integrations → Channels |
| `instagram_business_manage_messages` | Receive and reply to DMs in the shared inbox and automations | A customer DM arriving in the inbox and a reply being sent |
| `instagram_business_manage_comments` (if used) | Comment-to-DM automations, comment shield | A keyword comment triggering a private reply; a hidden comment |
| `instagram_business_content_publish` (if used) | Content calendar publishing | Scheduling and publishing a post |
| `pages_messaging` (Messenger) | Messenger inbox and automations | A Messenger conversation |

Request only the permissions the launch actually uses, and keep `META_SCOPES` in sync.

## Screencast script (one per permission)

1. Sign in to Instantlify and open Integrations → Channels.
2. Connect the test Instagram professional account through Meta's dialog.
3. From a separate Instagram account, send a DM; show it arriving in the inbox.
4. Reply from the inbox; show the reply on the phone.
5. For comments: publish a comment-to-DM automation, comment the keyword, show the
   private reply.
6. Show disconnecting the account, then removing the app in Instagram settings and the
   account showing as disconnected in Instantlify.

## Before submitting

- [ ] Business verification completed in Meta Business Manager
- [ ] Privacy policy and terms reviewed by a lawyer, company details filled in
- [ ] App in Live mode with the URLs above, test users added
- [ ] `META_APP_SECRET`, `META_WEBHOOK_VERIFY_TOKEN` and `PUBLIC_APP_URL` set in production
- [ ] Screencasts recorded on the production URL
