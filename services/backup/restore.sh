#!/bin/sh
# Restores one backup folder.  Stop the application containers first (see docs/operations.md):
#   docker compose stop api reports dms keycloak
#   docker compose exec backup restore.sh 20261103T020000Z            (into the live databases)
#   docker compose exec backup restore.sh 20261103T020000Z --scratch  (into *_restore_test copies)
set -eu
[ -f /etc/eax-backup.env ] && . /etc/eax-backup.env
STAMP="${1:?give the backup folder name, for example 20261103T020000Z}"
MODE="${2:-}"
SOURCE="/backups/$STAMP"
[ -d "$SOURCE" ] || { echo "No backup folder $SOURCE"; exit 1; }
export PGHOST=db PGUSER=postgres PGPASSWORD="${EAX_DB_SUPERUSER_PASSWORD}"

( cd "$SOURCE" && sha256sum -c SHA256SUMS ) || { echo "Checksum mismatch: not restoring"; exit 1; }

for DUMP in "$SOURCE"/*.dump; do
  DB=$(basename "$DUMP" .dump)
  if [ "$MODE" = "--scratch" ]; then
    TARGET_DB="${DB}_restore_test"
    dropdb --if-exists "$TARGET_DB"
    createdb "$TARGET_DB"
    echo "EA Explorer restore: $DB -> $TARGET_DB (scratch)"
    pg_restore --no-owner --dbname="$TARGET_DB" "$DUMP"
  else
    echo "EA Explorer restore: $DB (live)"
    pg_restore --clean --if-exists --dbname="$DB" "$DUMP"
  fi
done

if [ "$MODE" != "--scratch" ] && [ -f "$SOURCE/mayan-files.tar.gz" ]; then
  echo "Mayan files are archived in $SOURCE/mayan-files.tar.gz; restore them into EAX_DOCS_DIR (see docs/operations.md)."
fi
echo "EA Explorer restore: done"
