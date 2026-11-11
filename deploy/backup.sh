#!/bin/sh
# Timestamped pg_dump loop for the production stack.
#
# Runs as its own service so backups do not depend on anyone remembering a host cron.
# Dumps go to a named volume; copy them off this host as well, because a dump sitting
# on the machine that died is not a backup.
#
# BACKUP_INTERVAL_SECONDS  how often to dump (default daily)
# BACKUP_KEEP              how many dumps to keep (default 14)
set -eu

DIR=/backups
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
KEEP="${BACKUP_KEEP:-14}"

mkdir -p "$DIR"

while true; do
	stamp="$(date -u +%Y%m%dT%H%M%SZ)"
	target="$DIR/instantlify-$stamp.sql.gz"
	# Dump to a partial name and rename on success, so an interrupted dump is never
	# mistaken for a restorable backup.
	if pg_dump --format=plain --no-owner --no-privileges | gzip >"$target.partial"; then
		mv "$target.partial" "$target"
		echo "backup ok $target ($(wc -c <"$target") bytes)"
	else
		rm -f "$target.partial"
		echo "backup FAILED at $stamp" >&2
	fi
	# Prune oldest first, counting only completed dumps.
	ls -1t "$DIR"/instantlify-*.sql.gz 2>/dev/null | tail -n "+$((KEEP + 1))" | while read -r old; do
		rm -f "$old" && echo "pruned $old"
	done
	sleep "$INTERVAL"
done
