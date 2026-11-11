#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  echo '.env already exists; preserving your configuration.'
  exit 0
fi
umask 077
python3 - <<'PY'
import base64
import secrets
from pathlib import Path

value = Path('.env.example').read_text()
db = secrets.token_urlsafe(32)
replacements = {
    'DJANGO_SECRET_KEY=GENERATE_WITH_BOOTSTRAP': 'DJANGO_SECRET_KEY=' + secrets.token_urlsafe(64),
    'FIELD_ENCRYPTION_KEYS=GENERATE_WITH_BOOTSTRAP': 'FIELD_ENCRYPTION_KEYS=' + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    'POSTGRES_PASSWORD=GENERATE_WITH_BOOTSTRAP': 'POSTGRES_PASSWORD=' + db,
    'instantlify:GENERATE_WITH_BOOTSTRAP@postgres': f'instantlify:{db}@postgres',
    'local:GENERATE_WITH_BOOTSTRAP': 'local:' + secrets.token_urlsafe(24),
}
for old, new in replacements.items():
    value = value.replace(old, new)
with Path('.env').open('x') as output:
    output.write(value)
print('Created .env with random local secrets. Run docker compose up --build -d.')
PY
