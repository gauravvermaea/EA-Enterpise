#!/bin/sh
# EA Explorer infrastructure restore, the data part (phase 8.4, D216, D227). The operations helper runs it inside this
# container, after stopping the services that use what is restored:
#   restore.sh <folder> [--dbs a,b] [--files documents,tls] [--scratch]
#     --dbs      the databases to restore (default: every dump in the backup; "-" for none)
#     --files    the file sets to restore (documents: Mayan's files, tls: the certificate, reports: Superset's home,
#                imports and exports: the API's folders); a set the backup does not have is left as it is
# Each database goes to the server its service reads it from now: the library's and the views' to their own servers when
# EAX_LIBRARY_DB_HOST or EAX_VIEWS_DB_HOST say so, every other one to the main server (D410). The roles a database needs
# that the server does not have yet (a new server) are made from the backup's globals.sql first; roles that are there
# are left as they are (their passwords are this installation's).
#     --scratch  databases into <name>_restore_test copies instead of the live ones (a trial restore)
# Nothing live is touched until everything has been restored cleanly (D227):
#   * the checksums are checked first: nothing is restored from a damaged backup;
#   * each database is restored into <name>__restoring, stopping at the first error; only when every one is in are the
#     live ones renamed <name>__before and the restored ones given their names (with the live database's owner, grants
#     and settings); if any step fails, the ones already swapped are put back;
#   * each file set is unpacked beside the live files (.eax-restoring in the same folder), then swapped the same way.
# The __before copies are removed at the end. A failed restore leaves the installation as it was.
set -eu
[ -f /etc/eax-backup.env ] && . /etc/eax-backup.env
REL="${1:?give the backup folder, for example infrastructure/20261106T010000Z-nightly}"
shift
DBS="" ; FILES="" ; SCRATCH=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dbs) DBS="$2"; shift 2;;
    --files) FILES="$2"; shift 2;;
    --scratch) SCRATCH=1; shift;;
    *) echo "Unknown option $1"; exit 2;;
  esac
done
case "$REL" in *..*|/*) echo "A folder under the backups folder, please"; exit 2;; esac
SOURCE="${EAX_BACKUP_ROOT:-/backups}/$REL"
[ -d "$SOURCE" ] || { echo "No backup folder $SOURCE"; exit 1; }
export PGHOST="${EAX_BACKUP_PGHOST:-db}" PGPORT="${EAX_BACKUP_PGPORT:-5432}" PGUSER=postgres PGPASSWORD="${EAX_DB_SUPERUSER_PASSWORD:-}" PGOPTIONS="-c client_min_messages=warning"
say() { echo "restore: $*"; }
q() { psql -qAtX -v ON_ERROR_STOP=1 -d postgres -c "$1"; }
exists() { [ "$(q "SELECT 1 FROM pg_database WHERE datname = '$1'")" = "1" ]; }
kick() { q "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$1' AND pid <> pg_backend_pid()" >/dev/null; }
dest_of() { case "$1" in documents) echo "${EAX_BACKUP_DOCS:-/mayan}";; tls) echo "${EAX_BACKUP_TLS:-/tls}";;
  reports) echo "${EAX_BACKUP_REPORTS:-/superset-home}";; imports) echo "${EAX_BACKUP_IMPORTS:-/imports}";;
  exports) echo "${EAX_BACKUP_EXPORTS:-/exports}";; persist) echo "${EAX_BACKUP_PERSIST:-/persist}";; *) echo "";; esac; }
ALL_SETS="documents tls reports imports exports persist"
MAIN="$PGHOST $PGPORT"
# the server a database lives on now ("host port"): the library's and the views' may have their own (D410)
server_of() {
  if [ "$1" = "${EAX_LIBRARY_DB_NAME:-eaxlibrary}" ] || [ "$1" = "${EAX_LIBRARY_DB_NAME:-eaxlibrary}__restoring" ]; then
    echo "${EAX_LIBRARY_DB_HOST:-$PGHOST} ${EAX_LIBRARY_DB_PORT:-$PGPORT}"
  elif [ "$1" = "${EAX_VIEWS_DB_NAME:-eaxviews}" ] || [ "$1" = "${EAX_VIEWS_DB_NAME:-eaxviews}__restoring" ]; then
    echo "${EAX_VIEWS_DB_HOST:-$PGHOST} ${EAX_VIEWS_DB_PORT:-$PGPORT}"
  else echo "$MAIN"; fi
}
SERVERS=$(for N in "${EAX_LIBRARY_DB_NAME:-eaxlibrary}" "${EAX_VIEWS_DB_NAME:-eaxviews}"; do server_of "$N"; done; echo "$MAIN")
SERVERS=$(echo "$SERVERS" | sort -u | tr ' ' ':')
# runs a command against the server of database $1
at() { _hp=$(server_of "$1"); shift; ( PGHOST=${_hp% *}; PGPORT=${_hp#* }; export PGHOST PGPORT; "$@" ); }
# runs a command against server $1 ("host:port")
on() { _s=$1; shift; ( PGHOST=${_s%:*}; PGPORT=${_s##*:}; export PGHOST PGPORT; "$@" ); }
# the roles of a globals file that the server does not have yet are made from it (CREATE and ALTER ROLE lines only)
make_roles() {
  [ -f "$1" ] || return 0
  for R in $(awk '$1 == "CREATE" && $2 == "ROLE" { sub(/;$/, "", $3); print $3 }' "$1"); do
    NAME=$(echo "$R" | tr -d '"')
    [ "$(q "SELECT 1 FROM pg_roles WHERE rolname = '$NAME'")" = "1" ] && continue
    say "role $NAME: made from the backup (this server did not have it)"
    awk -v r="$R" '($1 == "CREATE" || $1 == "ALTER") && $2 == "ROLE" && ($3 == r || $3 == r";")' "$1" \
      | psql -qAtX -v ON_ERROR_STOP=1 -d postgres >/dev/null
  done
}
live() { find "$1" -mindepth 1 -maxdepth 1 ! -name .eax-restoring ! -name .eax-before; }

# ---------------------------------------------------------------- 0. heal what an interrupted restore left (D227)
# A restore can be run again and again: what an earlier one left half done is put right first.
heal_dbs() {
  for OLD in $(q "SELECT datname FROM pg_database WHERE datname LIKE '%\_\_before'"); do
    DB=${OLD%__before}
    if exists "$DB"; then q "DROP DATABASE \"$OLD\""; else say "database $DB: putting back the copy an interrupted restore left"; q "ALTER DATABASE \"$OLD\" RENAME TO \"$DB\""; fi
  done
  for OLD in $(q "SELECT datname FROM pg_database WHERE datname LIKE '%\_\_restoring'"); do q "DROP DATABASE \"$OLD\""; done
}
for S in $SERVERS; do on "$S" heal_dbs; done
for SET in $ALL_SETS; do
  DEST=$(dest_of "$SET"); [ -d "$DEST" ] || continue
  if [ -d "$DEST/.eax-before" ]; then
    if [ -z "$(live "$DEST")" ]; then
      say "files $SET: putting back the files an interrupted restore left"
      find "$DEST/.eax-before" -mindepth 1 -maxdepth 1 -exec mv {} "$DEST/" \;
    fi
    rm -rf "$DEST/.eax-before"
  fi
  rm -rf "$DEST/.eax-restoring"
done

say "checking the checksums of $REL"
( cd "$SOURCE" && sha256sum -c SHA256SUMS >/dev/null 2>&1 ) || { say "checksum mismatch: the backup is damaged, nothing restored"; exit 1; }

DUMPS="$SOURCE/databases"
[ -d "$DUMPS" ] || DUMPS="$SOURCE"          # backups made before phase 8.4 keep the dumps at the top
LIST=""
if [ "$DBS" != "-" ]; then
  for DUMP in "$DUMPS"/*.dump; do
    [ -f "$DUMP" ] || continue
    DB=$(basename "$DUMP" .dump)
    if [ -n "$DBS" ]; then case ",$DBS," in *",$DB,"*) ;; *) continue;; esac; fi
    LIST="$LIST $DB"
  done
fi

# ---------------------------------------------------------------- a trial restore into scratch copies
if [ -n "$SCRATCH" ]; then
  for DB in $LIST; do
    say "database $DB -> ${DB}_restore_test"
    at "$DB" q "DROP DATABASE IF EXISTS \"${DB}_restore_test\""; at "$DB" createdb -T template0 "${DB}_restore_test"
    at "$DB" pg_restore --no-owner --exit-on-error --dbname="${DB}_restore_test" "$DUMPS/$DB.dump"
  done
  say "done (scratch copies)"; exit 0
fi

SWAPPED=""        # databases already swapped in (put back on failure)
FILES_SWAPPED=""  # file sets already swapped in
rollback() {
  set +e
  for DB in $SWAPPED; do
    say "putting the database $DB back as it was"
    at "$DB" kick "$DB"; at "$DB" q "DROP DATABASE IF EXISTS \"$DB\""
    at "$DB" exists "${DB}__before" && at "$DB" q "ALTER DATABASE \"${DB}__before\" RENAME TO \"$DB\""
  done
  for SET in $FILES_SWAPPED; do
    DEST=$(dest_of "$SET")
    say "putting the $SET files back as they were"
    live "$DEST" | while read -r f; do rm -rf "$f"; done
    find "$DEST/.eax-before" -mindepth 1 -maxdepth 1 -exec mv {} "$DEST/" \;
  done
  for DB in $LIST; do at "$DB" q "DROP DATABASE IF EXISTS \"${DB}__restoring\"" >/dev/null 2>&1; done
  for SET in $(echo "$FILES" | tr ',' ' '); do
    DEST=$(dest_of "$SET"); [ -n "$DEST" ] && rm -rf "$DEST/.eax-restoring" "$DEST/.eax-before"
  done
  say "FAILED: nothing was changed; the databases and files are as they were before this restore"
}
trap 'rc=$?; if [ $rc -ne 0 ]; then rollback; fi; exit $rc' EXIT

# ---------------------------------------------------------------- 1. every database into <name>__restoring
# the roles the databases need, on a server that does not have them yet (a new server)
if [ -n "$LIST" ]; then
  on "$(echo "$MAIN" | tr ' ' ':')" make_roles "$DUMPS/globals.sql"
  for DB in $LIST; do
    [ "$(server_of "$DB")" = "$MAIN" ] && continue
    if [ -f "$DUMPS/globals-$DB.sql" ]; then at "$DB" make_roles "$DUMPS/globals-$DB.sql"; else at "$DB" make_roles "$DUMPS/globals.sql"; fi
  done
fi
for DB in $LIST; do
  say "database $DB: restoring into ${DB}__restoring$( [ "$(server_of "$DB")" = "$MAIN" ] || echo " (on $(server_of "$DB" | tr ' ' ':'))")"
  at "$DB" q "DROP DATABASE IF EXISTS \"${DB}__restoring\""
  OWNER=$(at "$DB" q "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = '$DB'")
  [ -n "$OWNER" ] || OWNER=$(pg_restore -C -l "$DUMPS/$DB.dump" | sed -n 's/.* DATABASE - [^ ]* \([^ ]*\)$/\1/p' | head -1)
  # a dump that does not name it: the role that owns most of what is in it
  [ -n "$OWNER" ] || OWNER=$(pg_restore -l "$DUMPS/$DB.dump" | awk '/^[0-9]+; [0-9]+ [0-9]+ (TABLE|SEQUENCE|VIEW|SCHEMA|FUNCTION) / { print $NF }' | sort | uniq -c | sort -rn | awk 'NR == 1 { print $2 }')
  [ -n "$OWNER" ] && [ "$(at "$DB" q "SELECT 1 FROM pg_roles WHERE rolname = '$OWNER'")" = "1" ] || OWNER=postgres
  at "$DB" createdb -T template0 -O "$OWNER" "${DB}__restoring"
  at "$DB" pg_restore --exit-on-error --single-transaction --dbname="${DB}__restoring" "$DUMPS/$DB.dump"
  say "database $DB: restored ($(at "$DB" q "SELECT pg_size_pretty(pg_database_size('${DB}__restoring'))"))"
done

# ---------------------------------------------------------------- 2. every file set unpacked beside the live files
for SET in $(echo "$FILES" | tr ',' ' '); do
  DEST=$(dest_of "$SET")
  [ -n "$DEST" ] || { say "unknown file set $SET"; exit 2; }
  ARCHIVE="$SOURCE/files/$SET.tar.gz"
  if [ "$SET" = documents ] && [ ! -f "$ARCHIVE" ]; then ARCHIVE="$SOURCE/mayan-files.tar.gz"; fi
  [ -f "$ARCHIVE" ] || { say "no $SET files in this backup: left as they are"; continue; }
  say "files $SET: unpacking"
  rm -rf "$DEST/.eax-restoring"; mkdir -p "$DEST/.eax-restoring"
  tar -C "$DEST/.eax-restoring" -xzf "$ARCHIVE"
done

# ---------------------------------------------------------------- 3. swap: the restored ones take the live names
for DB in $LIST; do
  say "database $DB: swapping in"
  at "$DB" q "DROP DATABASE IF EXISTS \"${DB}__before\""
  if at "$DB" exists "$DB"; then
    at "$DB" kick "$DB"
    at "$DB" q "ALTER DATABASE \"$DB\" RENAME TO \"${DB}__before\""
    SWAPPED="$SWAPPED $DB"
    # the live database's grants and settings go to the restored one
    at "$DB" q "DO \$\$ DECLARE r record; BEGIN
         FOR r IN SELECT a.grantee, a.privilege_type FROM pg_database d, aclexplode(d.datacl) a
                   WHERE d.datname = '${DB}__before' AND a.grantee <> 0 LOOP
           EXECUTE format('GRANT %s ON DATABASE %I TO %I', r.privilege_type, '${DB}__restoring', pg_get_userbyid(r.grantee));
         END LOOP;
         FOR r IN SELECT unnest(s.setconfig) AS c FROM pg_db_role_setting s JOIN pg_database d ON d.oid = s.setdatabase
                   WHERE d.datname = '${DB}__before' AND s.setrole = 0 LOOP
           EXECUTE format('ALTER DATABASE %I SET %s = %L', '${DB}__restoring', split_part(r.c, '=', 1),
                          substr(r.c, strpos(r.c, '=') + 1));
         END LOOP;
       END \$\$"
  else
    SWAPPED="$SWAPPED $DB"
  fi
  at "$DB" q "ALTER DATABASE \"${DB}__restoring\" RENAME TO \"$DB\""
done
for SET in $(echo "$FILES" | tr ',' ' '); do
  DEST=$(dest_of "$SET")
  [ -d "$DEST/.eax-restoring" ] || continue
  say "files $SET: swapping in"
  rm -rf "$DEST/.eax-before"; mkdir -p "$DEST/.eax-before"
  FILES_SWAPPED="$FILES_SWAPPED $SET"
  live "$DEST" | while read -r f; do mv "$f" "$DEST/.eax-before/"; done
  find "$DEST/.eax-restoring" -mindepth 1 -maxdepth 1 -exec mv {} "$DEST/" \;
  rmdir "$DEST/.eax-restoring"
done

# ---------------------------------------------------------------- 4. done: the copies from before go
trap - EXIT
for DB in $LIST; do at "$DB" q "DROP DATABASE IF EXISTS \"${DB}__before\""; done
for SET in $FILES_SWAPPED; do rm -rf "$(dest_of "$SET")/.eax-before"; done
say "done"
