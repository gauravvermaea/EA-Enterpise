#!/bin/sh
# The backup container waits for the operations helper to run backup.sh and restore.sh in it (phase 8.4, D216): the
# schedules are kept in the database and set on Administration > Backups (D222); the job runner starts them. What
# backup.sh needs from the environment is saved for docker exec.
set -eu
export -p | grep -E ' (EAX_|POSTGRES_)[A-Z_]*=' > /etc/eax-backup.env
chmod 600 /etc/eax-backup.env
echo "EA Explorer backup: ready (schedules: Administration > Backups)"
exec sleep infinity
