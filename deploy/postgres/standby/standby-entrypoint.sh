#!/bin/sh
# EA Explorer database standby (phase 36.3, D527). Waits for the primary, makes sure the replication login and its
# slot exist there, copies the primary once (pg_basebackup, which also writes standby.signal and how to reach the
# primary), then runs PostgreSQL as a hot standby that follows the primary continuously (read only).
set -eu
PGDATA="${PGDATA:-/var/lib/postgresql/data}"
echo "EA Explorer standby: waiting for the primary ${PRIMARY_HOST}:${PRIMARY_PORT}"
until pg_isready -h "$PRIMARY_HOST" -p "$PRIMARY_PORT" -U postgres >/dev/null 2>&1; do sleep 2; done
PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$PRIMARY_HOST" -p "$PRIMARY_PORT" -U postgres -d postgres -v ON_ERROR_STOP=1 \
  -v pw="$EAX_REPLICATION_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE eax_replicator WITH REPLICATION LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_replicator') \gexec
ALTER ROLE eax_replicator WITH REPLICATION LOGIN PASSWORD :'pw';
SELECT pg_create_physical_replication_slot('eax_standby') WHERE NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = 'eax_standby');
SQL
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  echo "EA Explorer standby: copying the primary (pg_basebackup); this takes a while for a large database"
  rm -rf "${PGDATA:?}"/* "${PGDATA:?}"/.[!.]* 2>/dev/null || true
  PGPASSWORD="$EAX_REPLICATION_PASSWORD" pg_basebackup -h "$PRIMARY_HOST" -p "$PRIMARY_PORT" -U eax_replicator \
    -D "$PGDATA" -X stream -R -S eax_standby
  chown -R postgres:postgres "$PGDATA"
  chmod 700 "$PGDATA"
fi
echo "EA Explorer standby: following the primary (read only)"
exec docker-entrypoint.sh postgres -c hot_standby=on -c hba_file=/eax-pg/pg_hba.conf
