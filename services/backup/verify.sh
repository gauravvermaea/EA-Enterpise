#!/bin/sh
# EA Explorer: check that an infrastructure backup can be restored, touching nothing live (R2.45; owner, 12 Nov 2026: "do
# u test application backup and infra backup in your testing? If not it should be"). The self-test runs it through the
# operations helper:   verify.sh <folder>      (for example infrastructure/20261112T200000Z-self-test-12)
#   1. the checksums (SHA256SUMS): every file as it was written
#   2. every file set (files/*.tar.gz): a readable archive
#   3. every database dump: restored into <name>_restore_test (restore.sh --scratch: left out of backups), its tables
#      counted against the live database's, and the scratch copy dropped
# Each check prints one line "CHECK<TAB>name<TAB>ok|failed<TAB>detail"; the exit code is 1 when any failed.
set -u
[ -f /etc/eax-backup.env ] && . /etc/eax-backup.env
REL="${1:?give the backup folder, for example infrastructure/20261112T200000Z-self-test}"
case "$REL" in *..*|/*) echo "A folder under the backups folder, please"; exit 2;; esac
SOURCE="${EAX_BACKUP_ROOT:-/backups}/$REL"
[ -d "$SOURCE" ] || { printf 'CHECK\tthe backup folder\tfailed\tno folder %s\n' "$REL"; exit 1; }
export PGHOST="${EAX_BACKUP_PGHOST:-db}" PGPORT="${EAX_BACKUP_PGPORT:-5432}" PGUSER=postgres PGPASSWORD="${EAX_DB_SUPERUSER_PASSWORD:-}" PGOPTIONS="-c client_min_messages=warning"
BAD=0
check() { printf 'CHECK\t%s\t%s\t%s\n' "$1" "$2" "$3"; [ "$2" = ok ] || BAD=1; }
tables() { psql -qAtX -d "$1" -c "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')" 2>/dev/null; }

if [ -f "$SOURCE/SHA256SUMS" ]; then
  # plain -c: BusyBox's sha256sum (the backup image is Alpine) has no --quiet; the lines that are not OK are the reason
  if out=$(cd "$SOURCE" && sha256sum -c SHA256SUMS 2>&1); then check "checksums" ok "$(wc -l < "$SOURCE/SHA256SUMS") files as written"
  else check "checksums" failed "$(echo "$out" | grep -v ': OK$' | head -3 | tr '\n' ';')"; fi
else
  check "checksums" failed "no SHA256SUMS in the backup"
fi

for A in "$SOURCE"/files/*.tar.gz; do
  [ -f "$A" ] || continue
  N=$(basename "$A" .tar.gz)
  if n=$(tar -tzf "$A" 2>/dev/null | wc -l) && gzip -t "$A" 2>/dev/null; then check "files $N" ok "$n entries readable"
  else check "files $N" failed "the archive cannot be read"; fi
done

for D in "$SOURCE"/databases/*.dump; do
  [ -f "$D" ] || continue
  DB=$(basename "$D" .dump)
  if ! err=$("${EAX_RESTORE_SH:-/usr/local/bin/restore.sh}" "$REL" --dbs "$DB" --files - --scratch 2>&1); then
    check "database $DB" failed "the trial restore stopped: $(echo "$err" | grep -v '^restore:' | tail -2 | tr '\n' ' ')"
  else
    live=$(tables "$DB"); got=$(tables "${DB}_restore_test")
    if [ -n "$got" ] && [ "$got" -gt 0 ] && { [ -z "$live" ] || [ "$got" -ge "$live" ]; }; then
      check "database $DB" ok "restored into a scratch copy: $got tables${live:+ (live: $live)}"
    else
      check "database $DB" failed "restored ${got:-0} tables, the live database has ${live:-?}"
    fi
  fi
  psql -qAtX -d postgres -c "DROP DATABASE IF EXISTS \"${DB}_restore_test\"" >/dev/null 2>&1
done
exit $BAD
