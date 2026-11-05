# Advanced Meta feature approvals

Platform owners manage workspace approvals in **Admin console → Meta / API ops → Advanced Meta access by workspace** (`/ops/?tab=operations`). Search by workspace name or UUID, enter a reason, and grant or revoke each feature. Approvals apply to all workspace members, subject to their existing workspace roles. Support and analyst operators can view approvals but cannot change them. Changes require the existing console MFA session and CSRF protection and are written to the platform audit log.

New and existing workspaces are restricted by default. Apply the database migration before deploying the code:

```sh
python manage.py migrate
```

No plan or customer-facing API can grant these approvals. A grant also does not override plan limits, platform pauses, connection status, or Meta OAuth permissions.

| Capability | Enforcement |
| --- | --- |
| `meta_analytics` | Connecting live follower statistics to a creator kit, refreshing them in the background, and displaying saved live statistics. Revocation suppresses saved statistics immediately and prevents new refresh requests; results from a fetch revoked during execution are discarded. Clearing the selected accounts remains allowed. |
| `meta_publishing` | Creating/editing scheduled posts, running queued publishing jobs, and each live Instagram publishing adapter operation. Revoked queued jobs fail with `capability_approval_required`; they are not automatically republished after reapproval. Cancellation remains allowed. |

Account connection, token refresh, comment replies, DM replies, and Nemio's internal message/funnel analytics retain their existing access rules. This change does not introduce Meta reach/impressions, Ads, or additional business reporting endpoints.

`GET /api/workspaces/{workspace_id}/status/` includes a `capabilities` map after checking workspace membership. Clients can use it to display approval states. Restricted API operations return HTTP 403 with `code: capability_approval_required` and the capability key. Existing role/membership checks still apply.

When implementing another advanced business feature, add a named capability to `apps/platform_ops/capabilities.py` and call `check_capability` in its authenticated API after membership checks. Use `has_capability` in its worker and immediately before provider calls, and recheck before saving or exposing analytics results. Registering a capability alone does not enforce a new endpoint. Request any additional Meta OAuth permissions only through the separately implemented authorization flow.

Revocation cannot recall a provider request already sent; it blocks subsequent checks and calls. Historical records remain stored. Manually entered creator-kit statistics are user content and are unaffected.
