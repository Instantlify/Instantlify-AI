# Instantlify domain and email

Confirmed public identity: **instantlify.com**, **support@instantlify.com**.
The application already uses this mailbox for help links, support/privacy contacts,
and the default transactional sender. Purchasing a mailbox does not configure SMTP
delivery or connect the website to a server.

## Hostinger + Contabo + Coolify (selected staging setup)

Use the standalone **`compose.coolify.yaml`**, not `compose.prod.yaml`, in Coolify.
Name the Coolify environment **dev** and application **instantlify-dev**. Keep its
Git source branch **dev** and its existing resource/storage identity. Renaming
the display labels does not require creating a new application or database.
Enable **Preserve repository during deployment** so the gateway configuration
and backup scripts mounted from Git remain available.
Coolify owns the public ports and TLS. The `gateway` service routes HTTP privately
to Django/Next.js and supports WebSockets; it publishes no host ports. Backend
services count two proxies: Coolify and the gateway. Keep the gateway reachable
only through Coolify's private network so forwarded headers remain trusted.

1. In Hostinger DNS, point A records `dev` and `ops.dev` to the Contabo
   public IPv4 address. Preserve Hostinger mail MX/TXT records. Do not point the
   bare production domain at staging unless that is an explicit launch decision.
2. In Coolify, create a Git-based Docker Compose application for
   `Instantlify/Instantlify-AI`, branch `dev`, with Compose file
   `/compose.coolify.yaml`. The file must first be committed and merged into
   dev. Do not select the default local Compose file.
3. Assign both `https://dev.instantlify.com` and
   `https://ops.dev.instantlify.com` to `gateway`, container port **80**.
   If Coolify's domain field encodes the target port, use `:80` as its documented
   internal container-port selector, not as a public port. Assign no public domain
   to backend, frontend, Redis, PostgreSQL, workers, migrations or backup services.
4. Set the non-secret settings from `deploy/staging.env.example` in Coolify.
   `INSTANTLIFY_ENV_FILE` and `ACME_EMAIL` are unused by this standalone stack. Backend
   settings use production mode and proxy depth 2. The file explicitly passes
   environment variables into the containers, without requiring a checked-in .env.
5. Enter fresh `DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEYS`, `POSTGRES_PASSWORD`,
   matching `DATABASE_URL`, `FLOWER_BASIC_AUTH`, and `EMAIL_HOST_PASSWORD` as
   Coolify secrets. Do not use the example placeholder strings as real secrets.
   Database URL uses host `postgres` and must match POSTGRES_DB/POSTGRES_USER.
6. Hostinger Email SMTP is configured as `smtp.hostinger.com`, port `587`,
   `EMAIL_USE_TLS=true`, username `support@instantlify.com`, and sender
   `Instantlify <support@instantlify.com>`. Enter the mailbox password only in
   Coolify. Verify the SMTP details in hPanel; if your purchased plan uses Titan
   or another mail product, use that product's settings instead.
7. Deploy, verify certificate issuance and readiness, then test delivery of an
   actual password-reset email. This configuration has not yet been deployed or
   verified against the Contabo server. Copy backups off the server as well.

Provider references: [Coolify domains](https://coolify.io/docs/core/networking/domains),
[Coolify Compose configuration](https://coolify.io/docs/services/configuration/docker-compose),
[Hostinger email configuration](https://www.hostinger.com/support/1575756-how-to-get-email-account-configuration-details-for-hostinger-email/).

The Compose file supports the primary app/admin hosts. Tenant-owned custom domains
need their own Coolify routing/certificate provisioning before white-label launch.

## Environment configuration

The following manual Compose instructions apply when running the existing Caddy
stack directly, outside Coolify. Use the Coolify instructions above for Contabo.

Use `deploy/staging.env.example` for `dev.instantlify.com` and
`deploy/production.env.example` for `instantlify.com`. Each includes the correct
public URL, allowed hosts, CSRF origins, secure WebSocket URL, callback URLs,
support and privacy contact, sender, certificate contact, and readiness URL.
The separate admin hosts are `ops.dev.instantlify.com` and
`ops.instantlify.com`. Local development continues using `.env` and localhost.

On the staging host, copy `deploy/staging.env.example` to `.env.staging` in the
repository root. On the production host, copy `deploy/production.env.example` to
`.env.production`. These actual environment files are ignored by Git.

Replace `GENERATE_WITH_BOOTSTRAP` placeholders with fresh secrets for each
environment: Django secret (at least 50 characters), field encryption key ring,
PostgreSQL password (also update DATABASE_URL), and Flower password. Follow the
key formats in the existing bootstrap script. Keep staging and production secrets
and data separate. Do not use the literal placeholders on a deployed server.

Supply SMTP host, port, TLS setting, username and password from the email provider.
The templates use STARTTLS on port 587, matching the existing application defaults;
confirm the provider supports these settings before use. Authorize
`support@instantlify.com` as the sender. Staging channel adapters start disabled;
production uses live adapters and requires the relevant integration credentials.

Validate and start staging:

```sh
docker compose --env-file .env.staging -p instantlify-staging -f compose.yaml -f compose.prod.yaml config --quiet
docker compose --env-file .env.staging -p instantlify-staging -f compose.yaml -f compose.prod.yaml up -d --build
```

For production, use `.env.production` and project name `instantlify-production`.
INSTANTLIFY_ENV_FILE makes the backend, migration job, workers and Compose interpolation
read the same environment file. Rebuild the frontend when its public values change.
These commands retain the existing containerized PostgreSQL deployment; RDS needs
a separate Compose change to remove local database dependencies and backup jobs.

Run the two deployments on separate hosts: both edge proxies bind ports 80/443,
and backend/frontend loopback ports also overlap on a shared host. Separate Compose
project names keep their data volumes distinct, but do not resolve port conflicts.

## DNS and provider setup

The destination server addresses and provider access are still needed. No DNS,
mail-routing, or hosting settings have been changed by these files.

| DNS name | Destination |
| --- | --- |
| `@` (`instantlify.com`) | Production server address or hosting-provider target |
| `ops` | Production server address or hosting-provider target |
| `dev` | Staging server address or hosting-provider target |
| `ops.dev` | Staging server address or hosting-provider target |

For a server with a public IPv4 address, these are A records; only add AAAA records
if the server has working public IPv6. Managed hosting may require a different
record type and target. This configuration uses the bare domain as the canonical
production address; `www` is not configured by these changes.

Preserve the email provider's MX records when configuring the website. Publish the
provider-supplied SPF, DKIM and DMARC records; their exact values depend on the
provider and cannot be inferred from the domain name. SMTP credentials belong only
in the deployment's secret environment, not source control.

Allow inbound HTTP/HTTPS to Caddy on the deployment hosts. Its existing configuration
obtains certificates for the app and admin hostnames once DNS resolves to the host.
Register the environment-specific OAuth callback URLs with the relevant providers.

Before launch, verify HTTPS, signup/login, password-reset email delivery and reset
links, inbox WebSockets, and `/health/ready/` using the deployed domain. A rendered
support link does not verify that the mailbox can send or receive email. Review the
existing privacy and terms pages before publishing; their legal company fields may
still require completion.
