# GitHub builds and Coolify rolling web deployments

## What changes

GitHub CI builds and tests images; the VPS pulls images rather than compiling Next.js
or installing Python dependencies. The new web image packages Django, Next.js and
the internal Nginx gateway as one rolling unit on container port **8080**. Workers,
the single scheduler, PostgreSQL, Redis and backups stay outside that unit.

The existing Compose resource remains supported. Merely switching it to image tags
does not enable rolling updates: Coolify's Docker Compose application type does not
support its application-level rolling sequence. Use a **Docker Image application**
for the new web tier. Do not delete or recreate the existing resource/data volumes.

Coolify starts a replacement web container while the previous one is serving traffic,
checks readiness, then removes the previous container. This targets uninterrupted HTTP
requests during compatible releases; it is not a guarantee against host failures,
broken schema changes, exhausted memory or long-lived WebSocket disconnections.
The VPS must have room to run two web containers at the same time.

## GitHub setup

1. Merge the CI repairs in PR #11 first. The release job depends on all three CI jobs.
2. Allow this repository's Actions token to publish organization packages in GHCR.
   Images remain private; do not change package visibility to work around auth errors.
3. CI publishes `ghcr.io/instantlify/instantlify-backend:sha-<commit>` and
   `ghcr.io/instantlify/instantlify-web:sha-<commit>`. The workflow summary records
   their immutable digests. An isolated image smoke test checks PostgreSQL, Redis,
   worker heartbeat, both web processes, Nginx configuration and graceful shutdown.
4. Same-repository PRs build/test SHA images but never update deployment channel tags
   or call Coolify. After a successful push to staging, the verified web image also
   gets `:dev`; main gets `:production` using production frontend URLs.
5. In GitHub Settings → Environments, create **dev** and **production**. Each can
   supply `COOLIFY_DEPLOY_WEBHOOK` and `COOLIFY_API_TOKEN` secrets for the appropriate
   Docker Image application. Copy the authenticated deploy webhook from Coolify.
   Configure production approval protection if your GitHub plan supports it.
6. The workflow calls that webhook only after CI, image builds and image smoke checks
   succeed. With no webhook/token, it publishes images and explicitly skips deployment.

The total CI/build time still exists, but the running application serves traffic
throughout it. Pull/start/health checks become the deployment work on the VPS.
Do not enable image pruning that can delete the currently deployed/rollback image.

## Existing dev resource: preserve data and background services

The initial conversion is an operator migration, not an automatic repository change.
Keep the existing application serving while preparing a second Docker Image resource.

- Keep PostgreSQL/Redis and their current volumes, secrets, encryption keys, Celery
  queues, workers, and **one** Beat scheduler. Do not launch a second data stack.
- The new image must join the existing application's private Docker network through
  Coolify's supported networking/custom options. Inspect the actual network name in
  Coolify; do not guess it from a service label. Do not publish database/Redis ports.
- Use the current database connection and Redis/Celery URLs, adjusted only if the
  network requires the existing service's unique alias. Do not regenerate credentials.
- Shared user files must remain available to both versions. The current backend uses
  local media for attachments; use shared persistent storage or object storage before
  routing upload traffic to rolling replicas. Configure that same media storage on
  both the old and replacement containers and on any workers that read it.
- Update worker/Beat images separately to the matching immutable backend digest after
  compatibility is established. Restart the existing scheduler; never start two Beat
  instances. Celery tasks and queue payloads must work with both releases during overlap.

## Create the rolling web application in Coolify

1. Create a **Docker Image** application in environment **dev**. Use
   `ghcr.io/instantlify/instantlify-web:dev` once its verified image is published.
   For a controlled production release/rollback, prefer the recorded SHA tag/digest.
2. Authenticate Coolify to private GHCR with a credential permitted to read these
   packages. Enter it directly in Coolify's registry settings, not the repository.
3. Set **Ports Exposes = 8080** and leave host port mappings empty. Do not set a
   custom/consistent container name or fixed IP; those disable overlapping replicas.
4. Copy the current runtime environment and configure:

   ```dotenv
   DJANGO_SETTINGS_MODULE=config.settings.production
   APP_DOMAIN=dev.instantlify.com
   PLATFORM_ADMIN_HOST=ops.dev.instantlify.com
   PUBLIC_APP_URL=https://dev.instantlify.com
   TRUSTED_PROXY_DEPTH=2
   MIGRATE_ON_START=true
   ```

   The image already compiles internal frontend requests for loopback backend port
   8000. Runtime `NEXT_PUBLIC_*` changes do not rebuild the image: build a new release
   for changed public URLs. Keep SMTP, Stripe and provider credentials as runtime-only
   secrets; they are not sent to Docker builds by this workflow.
5. Keep the image's Docker health check. It requires backend DB/cache/worker readiness
   **and** a responding frontend, not just a running process. Set startup allowance
   high enough for the first migration. Configure **Stop Grace Period = 60 seconds**.
6. Join the existing private data-service network and configure shared media storage.
   Start the new resource without replacing the old one. Validate it using an
   explicitly configured temporary app/admin hostname and its matching runtime hosts.
7. Plan and test the initial domain handoff in Coolify. Creating a second resource with
   duplicate production hostnames is not an atomic cutover. Do not promise an
   uninterrupted initial handoff until the chosen proxy/routing procedure is tested.
   Keep the old resource/data services available for rollback. Normal deployments
   *within the new Docker Image resource* use Coolify's rolling replacement sequence.
8. After the cutover, keep background/data services and backups in the existing Compose
   resource. Disable its Git auto-deploy trigger so merging app code does not restart
   that stack. The new Docker Image app is deployed by the CI webhook after verification.

The new supervisor runs migrations before starting web processes, using a PostgreSQL
advisory lock to serialize concurrent replica starts. This does not make incompatible
migrations safe. Use additive/expand-contract schema changes; postpone drops/renames
until every old web/worker replica is gone. Rollbacks must use a schema-compatible image.

## Prove the cutover

Continuously request the app and an authenticated API during a representative release;
record failed requests rather than relying only on a green deployment badge. Confirm
the log order is replacement-start → readiness-success → old-container-stop. Also
test sessions, uploads, background jobs, WebSocket reconnection, and rollback. Keep the
old image serving if the replacement fails readiness. A single VPS still needs host
maintenance/recovery planning independently of deployment overlap.

References: [Coolify rolling requirements](https://coolify.io/docs/applications/deployments/rolling-updates),
[prebuilt Docker images](https://coolify.io/docs/applications/deployments/docker-image),
[external deployment triggers](https://coolify.io/docs/applications/deployments/automatic-deployments).
