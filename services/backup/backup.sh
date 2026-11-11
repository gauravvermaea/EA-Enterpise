#!/bin/sh
# EA Explorer infrastructure backup, the data part (phase 8.4, D216). The operations helper runs it inside this container:
#   backup.sh <folder>        writes into ${EAX_BACKUP_ROOT:-/backups}/<folder> (for example infrastructure/20261106T010000Z-nightly):
#     databases/<name>.dump   every database on the server (custom format), and databases/globals.sql (roles): the
#                             main one (eaexplorer), Keycloak's, Superset's, Mayan's, the library's and the views'
#     databases/HOSTS         the library's or the views' database when it is on a server of its own (EAX_LIBRARY_DB_HOST,
#                             EAX_VIEWS_DB_HOST): "<name> <host> <port>", its dump beside the others and its server's roles
#                             in databases/globals-<name>.sql (D410)
#     files/documents.tar.gz  Mayan's document files;  files/tls.tar.gz  the site certificate and key
#     files/reports.tar.gz    Superset's home (its secret key and uploads; its dashboards are in its database)
#     files/imports.tar.gz, files/exports.tar.gz   the API's import and export folders (files uploaded and made)
#     files/persist.tar.gz    persist/: the settings that survive resets (schedules, the banner; D558)
#     SHA256SUMS              a checksum of every file in the folder (the helper's code/ and config/ included)
# The helper writes code/, config/ and manifest.json around it. Nothing is deleted here (retention: the helper).
set -eu
[ -f /etc/eax-backup.env ] && . /etc/eax-backup.env
REL="${1:?give the folder under /backups}"
case "$REL" in *..*|/*) echo "A folder under /backups, please"; exit 2;; esac
TARGET="${EAX_BACKUP_ROOT:-/backups}/$REL"
mkdir -p "$TARGET/databases" "$TARGET/files"
export PGHOST="${EAX_BACKUP_PGHOST:-db}" PGPORT="${EAX_BACKUP_PGPORT:-5432}" PGUSER=postgres PGPASSWORD="${EAX_DB_SUPERUSER_PASSWORD:-}"

# the library's and the views' databases when they are on a server of their own (D410): "<name> <host> <port>"
ELSEWHERE=""
for KIND in LIBRARY VIEWS; do
  eval H=\${EAX_${KIND}_DB_HOST:-\$PGHOST} P=\${EAX_${KIND}_DB_PORT:-\$PGPORT}
  [ "$KIND" = LIBRARY ] && N=${EAX_LIBRARY_DB_NAME:-eaxlibrary} || N=${EAX_VIEWS_DB_NAME:-eaxviews}
  if [ "$H:$P" = "$PGHOST:$PGPORT" ]; then continue; fi
  ELSEWHERE="$ELSEWHERE $N"
  echo "$N $H $P" >> "$TARGET/databases/HOSTS"
done

for DB in $(psql -Atc "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' AND datname !~ '(__restoring|__before|_restore_test)$' ORDER BY 1"); do
  case " $ELSEWHERE " in *" $DB "*) continue;; esac      # its own server's copy is the live one
  echo "backup: database $DB"
  pg_dump --format=custom --file="$TARGET/databases/$DB.dump" "$DB"
done
pg_dumpall --globals-only > "$TARGET/databases/globals.sql"
if [ -f "$TARGET/databases/HOSTS" ]; then
  while read -r N H P; do
    echo "backup: database $N (on $H:$P)"
    pg_dump --host="$H" --port="$P" --format=custom --file="$TARGET/databases/$N.dump" "$N"
    pg_dumpall --host="$H" --port="$P" --globals-only > "$TARGET/databases/globals-$N.sql"
  done < "$TARGET/databases/HOSTS"
fi

if [ -d "${EAX_BACKUP_DOCS:-/mayan}" ] && [ "$(ls -A "${EAX_BACKUP_DOCS:-/mayan}" 2>/dev/null)" ]; then
  echo "backup: document files"
  tar -C "${EAX_BACKUP_DOCS:-/mayan}" --exclude=./.eax-restoring --exclude=./.eax-before -czf "$TARGET/files/documents.tar.gz" .
fi
# the other file sets: name and folder (each only when this container has it and it is not empty)
for SET in "tls ${EAX_BACKUP_TLS:-/tls}" "reports ${EAX_BACKUP_REPORTS:-/superset-home}" \
           "imports ${EAX_BACKUP_IMPORTS:-/imports}" "exports ${EAX_BACKUP_EXPORTS:-/exports}" \
           "persist ${EAX_BACKUP_PERSIST:-/persist}"; do
  NAME=${SET%% *} DIR=${SET#* }
  if [ -d "$DIR" ] && [ "$(ls -A "$DIR" 2>/dev/null)" ]; then
    echo "backup: files $NAME"
    # persist/'s safety-backups/ are backups themselves: left out (D558)
    tar -C "$DIR" --exclude=./.eax-restoring --exclude=./.eax-before --exclude=./safety-backups -czf "$TARGET/files/$NAME.tar.gz" .
  fi
done

( cd "$TARGET" && find . -type f ! -name SHA256SUMS ! -name manifest.json ! -name PINNED | sed 's|^\./||' | sort | xargs sha256sum > SHA256SUMS )
echo "backup: done $TARGET"
