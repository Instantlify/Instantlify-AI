# Authentication email templates

Apply migration `platform_ops.0015_email_verification_template` and deploy both backend and Celery workers. The migration creates the active verification template if missing and preserves existing operator edits and draft status. The other authentication templates already exist in the registry.

Manage subjects, message copy and active/draft status in the admin console under Email Templates. Changes are read when an email is sent; no frontend deployment is needed for copy edits. Keep template names stable because they identify the sending flow.

| Template | Trigger | Variables |
| --- | --- | --- |
| `email-verification` | Registration and resend verification | `name`, `email`, `link` |
| `password-reset` | Password reset request | `name`, `email`, `link` |
| `magic-link-signin` | Magic-link delivery worker | `name`, `email`, `link` |
| `email-change-confirmation` | Confirmation sent to a changed account email | `name`, `email`, `link` |
| `email-change-notice-current` | Change notice sent to the previous verified email address | `name`, `new_email`, `support_email` |

All emails using the transactional template sender now have a shared Instantlify HTML layout and a plain-text alternative, including existing invitation, welcome and billing emails. The editor body is text: paragraphs and links are formatted safely in HTML, and user-provided values are escaped. Known action links appear as buttons in HTML and remain full links in plain text. If a valid action link is missing from edited copy, the sender appends it to the text version so it remains usable.

Draft or missing templates are not sent; authentication endpoints retain generic responses so their status does not disclose account existence. Verification and password-reset failures emit `verification_email_failed` / `password_reset_email_failed` without including the email address or token. Magic-link SMTP retries remain in place, and a draft/missing template emits `magic_link_template_unavailable` without bypassing the operator's choice.

Verification links still expire after three days, password-reset links use the configured one-hour timeout, and magic links remain single-use with a 15-minute expiry. Existing token formats and verification rules are unchanged. Local tests use an in-memory email backend; live inbox delivery still depends on deployment SMTP configuration and provider acceptance.
