#!/bin/sh
# Schedules backup.sh with the cron expression from eaexplorer.env (EAX_BACKUP_SCHEDULE).
set -eu
SCHEDULE="${EAX_BACKUP_SCHEDULE:-0 2 * * *}"
mkdir -p /etc/crontabs
echo "$SCHEDULE /usr/local/bin/backup.sh >> /proc/1/fd/1 2>&1" > /etc/crontabs/root
# crond does not pass the container environment to jobs: save what backup.sh needs.
export -p | grep -E ' (EAX_|POSTGRES_)[A-Z_]*=' > /etc/eax-backup.env
chmod 600 /etc/eax-backup.env
echo "EA Explorer backup: scheduled '$SCHEDULE'; keeping ${EAX_BACKUP_KEEP_DAILY:-7} days"
exec crond -f -l 2
