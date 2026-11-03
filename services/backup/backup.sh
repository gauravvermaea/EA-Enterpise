#!/bin/sh
# Backs up all four databases (custom format) and Mayan's document files into one dated folder.
#   Run on a schedule by the backup container, or now:  docker compose exec backup backup.sh
set -eu
[ -f /etc/eax-backup.env ] && . /etc/eax-backup.env

export PGHOST=db PGUSER=postgres PGPASSWORD="${EAX_DB_SUPERUSER_PASSWORD}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARGET="/backups/$STAMP"
mkdir -p "$TARGET"

for DB in "${EAX_DB_NAME:-eaexplorer}" keycloak superset mayan; do
  echo "EA Explorer backup: dumping $DB"
  pg_dump --format=custom --file="$TARGET/$DB.dump" "$DB"
done
pg_dumpall --globals-only > "$TARGET/globals.sql"

if [ -d /mayan ] && [ "$(ls -A /mayan 2>/dev/null)" ]; then
  echo "EA Explorer backup: archiving Mayan document files"
  tar -C /mayan -czf "$TARGET/mayan-files.tar.gz" .
fi

( cd "$TARGET" && sha256sum * > SHA256SUMS )
echo "{\"created\":\"$STAMP\",\"version\":\"${EAX_VERSION:-dev}\",\"deployment\":\"${EAX_DEPLOYMENT:-laptop}\"}" > "$TARGET/manifest.json"

# Retention: remove backup folders older than EAX_BACKUP_KEEP_DAILY days
KEEP="${EAX_BACKUP_KEEP_DAILY:-7}"
find /backups -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP" -exec rm -rf {} + 2>/dev/null || true
echo "EA Explorer backup: done -> $TARGET"
