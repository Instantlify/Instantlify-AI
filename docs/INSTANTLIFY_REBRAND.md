# Instantlify branding

The product's only name is Instantlify. Every display string, identifier, header, storage key, Stripe product/metadata key, signed-link salt, tenant trigger prefix, automation export format, connector node/credential type, DNS challenge record and filename uses the Instantlify spelling. No earlier product name remains in the codebase, and nothing accepts one as an alias.

Set the confirmed public contact details through `INSTANTLIFY_SUPPORT_EMAIL` and `INSTANTLIFY_PRIVACY_EMAIL`. Optional external policy links use `INSTANTLIFY_PRIVACY_URL` and `INSTANTLIFY_TERMS_URL`. Docker build/runtime configuration passes these values through. The production identity is `instantlify.com` with `support@instantlify.com` as the default support/privacy contact. Development `PUBLIC_APP_URL` remains local.

Custom-domain DNS verification uses a TXT record at `_instantlify-challenge.<domain>` containing `instantlify-verify=<token>`, or a CNAME to the configured platform target.

Webhook deliveries carry `X-Instantlify-Event`, `X-Instantlify-Delivery`, `X-Instantlify-Signature` and, when configured, `X-Instantlify-Token`.

`platform_ops.0013_instantlify_brand` is an empty migration kept so the migration graph stays intact.
