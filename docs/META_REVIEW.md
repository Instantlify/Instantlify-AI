# Meta integration: external gate

**Status: not registered or submitted by this build.** Creating an app and submitting business identity/review material requires the business owner's Meta account. Local connection tests do not authorize access to real accounts.

## Start now

1. In the business's Meta developer account, create the app for the intended business use case and add the Instagram API/messaging capability available in the dashboard.
2. Choose the login product deliberately. The current scaffold targets **Instagram API with Instagram Login** and its `instagram_business_basic` / `instagram_business_manage_messages` permissions. Do not mix this token flow with Facebook Login's Page token model. Confirm the exact requirements in the dashboard for this app before enabling live exchange.
3. Prepare a Business/Creator Instagram test account and add the relevant app roles/testers.
4. Choose a public HTTPS staging domain. Register the exact callback URL, prepare webhook verification and subscribe to only the required events after Phase 1 endpoints exist.
5. Prepare a truthful privacy policy, support contact, terms, data deletion instructions/callback and data-retention policy using the business's actual legal details. Do not publish a generic placeholder as a completed compliance policy.
6. Record a real end-to-end screencast: account connection → consent → a user-initiated Instagram DM → workspace inbox → a delivered reply. Include only the permissions the product actually uses.
7. Submit for the required access level in the app dashboard as soon as that real flow works, and track the submission and reviewer feedback here.

## Evidence log

| Item | Status |
| --- | --- |
| App ID / business owner | Required from business |
| Business verification | Not assessed |
| Registered HTTPS domain / redirect | Pending |
| Privacy / deletion URLs | Pending actual business details and deployment |
| Live OAuth and token refresh | Phase 1 implementation |
| Real webhook + outbound message proof | Phase 1 verification |
| Screencast | Pending real flow |
| Advanced access submission | Not submitted |

Meta's review outcome and processing time cannot be guaranteed. A local fake or a screenshot of this foundation dashboard does not satisfy the live messaging exit criterion.

References checked while building: [Meta's official Instagram API collection](https://www.postman.com/meta/instagram/folder/1z5vxzu/instagram-api-with-instagram-login), [Meta's official API overview](https://www.postman.com/meta/workspace/instagram/documentation/23987686-9386f468-7714-490f-9bfc-9442db5c8f00). Recheck official documentation and the app dashboard at live implementation because products, permissions and limits change.
