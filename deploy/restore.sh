#!/bin/sh
# Restore a dump produced by backup.sh. Destructive: it drops and recreates the
# schema, so every row written since that dump is lost.
#
#   docker compose -f compose.yaml -f compose.prod.yaml run --rm \
#     -e CONFIRM_RESTORE=yes backup /restore.sh /backups/nemio-<stamp>.sql.gz
#
# Stop the backend, worker and beat first: restoring underneath a running app leaves
# it holding rows that no longer exist.
set -eu

dump="${1:?Pass the dump to restore, e.g. /backups/nemio-20260101T000000Z.sql.gz}"
[ -f "$dump" ] || { echo "No such dump: $dump" >&2; exit 1; }
if [ "${CONFIRM_RESTORE:-}" != "yes" ]; then
	echo "Refusing to restore: this drops the current database." >&2
	echo "Re-run with CONFIRM_RESTORE=yes once you are sure." >&2
	exit 1
fi

echo "Restoring $dump into ${PGDATABASE:-the configured database}…"
# Recreate the schema rather than restoring over it, so rows deleted since the dump
# do not survive the restore.
psql --quiet --set ON_ERROR_STOP=1 -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
gzip -dc "$dump" | psql --quiet --set ON_ERROR_STOP=1
echo "Restore complete. Start the backend and run: manage.py migrate --noinput"
