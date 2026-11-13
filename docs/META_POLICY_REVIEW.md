# Meta policy and deletion setup

Instantlify is a product of SKY INNOVA SERVICES (PRIVATE) LIMITED. The public
operator/address/contact details are centralized in `frontend/lib/legal.ts`.
Publish only the company information the operator supplied; incorporation and
tax identifiers are intentionally omitted.

## Dashboard URLs after deployment

For the development Meta app:

| Setting | URL |
| --- | --- |
| Privacy policy | https://dev.instantlify.com/privacy/ |
| Terms | https://dev.instantlify.com/terms/ |
| User data deletion instructions | https://dev.instantlify.com/data-deletion/ |
| Data deletion callback, when callback mode is selected | https://dev.instantlify.com/webhooks/meta/data-deletion/ |
| Deauthorization callback | https://dev.instantlify.com/webhooks/meta/deauthorize/ |

For the production Meta app, replace `dev.instantlify.com` with `instantlify.com`
and verify the actual production host before saving. The instructions page and
POST callback are different endpoints. Check all public pages without logging in,
including on mobile, and verify HTTPS and the footer links. Keep each Meta app's
domains, redirect URIs, permissions and secrets aligned with its environment.
This change does not modify CI or production deployment configuration.

## What is covered

- Public privacy, terms and deletion pages identify the operator and provide
  support@instantlify.com and +92 324 8686799.
- Privacy describes data categories, Meta permissions and uses, sharing, optional
  AI processing, retention, security, rights, revocation and deletion.
- Deletion requests can be made without a login or paid subscription. Removing
  an integration alone is distinguished from erasing its historical data.
- Callbacks verify HMAC-SHA256 against the applicable provider app secret, stop
  access, return a confirmation code/status URL and queue scoped erasure. The
  status endpoint exposes no subject identifier or internal review details.
- Exact callback retries are idempotent. A retry cannot disconnect a later
  reconnection. OAuth stores the authorizer identifier needed to map a request
  to a connected account; legacy or manual connections may require verification.
- Successful erasure removes connection-linked conversations, messages and
  derived records, clears affected export snapshots and checks shared contacts,
  financial records, active workers and downstream copies before completion.
  Ambiguous/retained data stays under review; token removal alone is not erasure.

## Operations required

Deploy migrations, web/API, Celery workers and beat together. Beat dispatches
pending requests every five seconds. Monitor unresolved cases promptly:

```sh
python manage.py review_meta_deletion
```

An unmatched app-scoped user ID, shared contact, financial retention requirement,
active job, interrupted worker or previously forwarded external copy requires a
privacy operator to verify ownership/scope, perform any necessary manual erasure,
coordinate with the relevant recipient and document lawful exceptions. Contact
the requester when additional proof is needed. Do not request passwords or tokens.
The public status deliberately remains under review during this work.

After resolving a temporary blocker, retry the automated scope:

```sh
python manage.py review_meta_deletion CONFIRMATION_CODE --retry
```

Only after independently verifying erasure and any lawful retention, record the
manual outcome with a non-personal internal reference:

```sh
python manage.py review_meta_deletion CONFIRMATION_CODE --confirm-erasure --reason "Privacy case reference: erasure and retention independently verified."
```

**This command records an attestation; it does not itself erase data.** Review
legacy requests as well: they are not assumed complete merely because the old
implementation removed tokens. Reapply applicable deletion requests to restored
backups before ordinary use; backup rotation and this restore procedure remain
deployment/operator responsibilities. Honor applicable legal request deadlines.

## Review boundaries

These changes prepare the application for review; they do not guarantee Meta
approval or replace legal review. Verify actual hosting/AI/email vendors,
retention settings, backup procedures and international-transfer arrangements
against the policy before production. Meta business verification, app review,
approved permissions, screencasts/test access and live-mode eligibility are
separate tasks. Never claim a permission or integration is approved merely
because a policy page exists.

Authoritative references to check against the current Meta Dashboard:

- https://developers.facebook.com/terms/
- https://developers.facebook.com/devpolicy/
- https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback/
- https://developers.facebook.com/docs/development/terms-and-policies/privacy-policy/
- https://about.fb.com/news/2020/07/improving-data-limits-simplifying-terms/

Several canonical developer pages rate-limited automated retrieval during this
update. Review their latest requirements directly before submitting the app.
