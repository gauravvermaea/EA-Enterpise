#!/bin/sh
# EA Explorer infrastructure backup, the data part (phase 8.4, D216). The operations helper runs it inside this container:
#   backup.sh <folder>        writes into ${EAX_BACKUP_ROOT:-/backups}/<folder> (for example infrastructure/20261106T010000Z-nightly):
#     databases/<name>.dump   every database on the server (custom format), and databases/globals.sql (roles)
#     files/documents.tar.gz  Mayan's document files;  files/tls.tar.gz  the site certificate and key
#     SHA256SUMS              a checksum of every file in the folder (the helper's code/ and config/ included)
# The helper writes code/, config/ and manifest.json around it. Nothing is deleted here (retention: the helper).
set -eu
[ -f /etc/eax-backup.env ] && . /etc/eax-backup.env
REL="${1:?give the folder under /backups}"
case "$REL" in *..*|/*) echo "A folder under /backups, please"; exit 2;; esac
TARGET="${EAX_BACKUP_ROOT:-/backups}/$REL"
mkdir -p "$TARGET/databases" "$TARGET/files"
export PGHOST="${EAX_BACKUP_PGHOST:-db}" PGPORT="${EAX_BACKUP_PGPORT:-5432}" PGUSER=postgres PGPASSWORD="${EAX_DB_SUPERUSER_PASSWORD:-}"

for DB in $(psql -Atc "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' AND datname !~ '(__restoring|__before|_restore_test)$' ORDER BY 1"); do
  echo "backup: database $DB"
  pg_dump --format=custom --file="$TARGET/databases/$DB.dump" "$DB"
done
pg_dumpall --globals-only > "$TARGET/databases/globals.sql"

if [ -d "${EAX_BACKUP_DOCS:-/mayan}" ] && [ "$(ls -A "${EAX_BACKUP_DOCS:-/mayan}" 2>/dev/null)" ]; then
  echo "backup: document files"
  tar -C "${EAX_BACKUP_DOCS:-/mayan}" --exclude=./.eax-restoring --exclude=./.eax-before -czf "$TARGET/files/documents.tar.gz" .
fi
if [ -d "${EAX_BACKUP_TLS:-/tls}" ] && [ "$(ls -A "${EAX_BACKUP_TLS:-/tls}" 2>/dev/null)" ]; then
  echo "backup: certificate"
  tar -C "${EAX_BACKUP_TLS:-/tls}" -czf "$TARGET/files/tls.tar.gz" .
fi

( cd "$TARGET" && find . -type f ! -name SHA256SUMS ! -name manifest.json ! -name PINNED | sed 's|^\./||' | sort | xargs sha256sum > SHA256SUMS )
echo "backup: done $TARGET"
