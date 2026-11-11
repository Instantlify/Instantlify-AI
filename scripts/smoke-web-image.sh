#!/usr/bin/env bash
# Isolated ephemeral CI stack: never connects to deployed databases or providers.
set -euo pipefail
web_image="${1:?Supply the web image}"
backend_image="${2:?Supply the backend image}"
prefix="instantlify-smoke-${GITHUB_RUN_ID:-$$}"
env_file="$(mktemp)"
cleanup() {
  result=$?
  if [[ "$result" != 0 ]]; then
    for service in web worker beat; do docker logs "$prefix-$service" 2>&1 || true; done
  fi
  for service in web worker beat postgres redis; do docker rm -fv "$prefix-$service" >/dev/null 2>&1 || true; done
  docker network rm "$prefix" >/dev/null 2>&1 || true
  rm -f "$env_file"
}
trap cleanup EXIT
python3 - "$env_file" <<'PY'
import base64
import secrets
import sys
from pathlib import Path

values = {
    'DJANGO_SETTINGS_MODULE': 'config.settings.production',
    'DJANGO_SECRET_KEY': secrets.token_urlsafe(64),
    'FIELD_ENCRYPTION_KEYS': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    'DATABASE_URL': 'postgresql://smoke:smoke-only-password@postgres:5432/smoke',
    'REDIS_URL': 'redis://redis:6379/0',
    'CELERY_BROKER_URL': 'redis://redis:6379/1',
    'CELERY_RESULT_BACKEND': 'redis://redis:6379/2',
    'APP_DOMAIN': 'smoke.invalid',
    'PUBLIC_APP_URL': 'https://smoke.invalid',
    'PLATFORM_ADMIN_HOST': 'ops.smoke.invalid',
    'ALLOWED_HOSTS': 'smoke.invalid,ops.smoke.invalid',
    'CSRF_TRUSTED_ORIGINS': 'https://smoke.invalid,https://ops.smoke.invalid',
    'TRUSTED_PROXY_DEPTH': '2',
    'CHANNEL_ADAPTER_MODE': 'disabled',
    'EMAIL_HOST': 'smtp.invalid',
}
Path(sys.argv[1]).write_text(''.join(f'{key}={value}\n' for key, value in values.items()))
PY
docker network create "$prefix" >/dev/null
docker run -d --name "$prefix-postgres" --network "$prefix" --network-alias postgres \
  -e POSTGRES_DB=smoke -e POSTGRES_USER=smoke -e POSTGRES_PASSWORD=smoke-only-password \
  pgvector/pgvector:pg17 >/dev/null
docker run -d --name "$prefix-redis" --network "$prefix" --network-alias redis redis:7.4-alpine >/dev/null
for attempt in $(seq 1 60); do
  if docker exec "$prefix-postgres" pg_isready -U smoke -d smoke; then break; fi
  sleep 1
done
docker run --rm --network "$prefix" --env-file "$env_file" "$backend_image" python manage.py migrate --noinput
docker run -d --name "$prefix-worker" --network "$prefix" --env-file "$env_file" \
  "$backend_image" celery -A config worker --loglevel=WARNING --concurrency=1 >/dev/null
docker run -d --name "$prefix-beat" --network "$prefix" --env-file "$env_file" \
  "$backend_image" celery -A config beat --loglevel=WARNING --schedule=/tmp/smoke-beat >/dev/null
docker run -d --name "$prefix-web" --network "$prefix" --env-file "$env_file" "$web_image" >/dev/null
ready=false
for attempt in $(seq 1 90); do
  if [[ "$(docker inspect --format '{{.State.Running}}' "$prefix-web")" != true ]]; then
    echo 'Web process exited before readiness.' >&2
    exit 1
  fi
  if docker exec "$prefix-web" python /app/deploy/health.py 2>/dev/null; then ready=true; break; fi
  sleep 2
done
[[ "$ready" == true ]]
docker exec "$prefix-web" nginx -t -c /tmp/instantlify-nginx.conf
docker stop --time 60 "$prefix-web" >/dev/null
[[ "$(docker inspect --format '{{.State.ExitCode}}' "$prefix-web")" == 0 ]]
echo 'Combined web readiness, dependency connections, Nginx config and graceful shutdown passed.'
