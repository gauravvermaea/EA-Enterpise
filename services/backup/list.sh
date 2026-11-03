#!/bin/sh
# Lists backup folders with their size:  docker compose exec backup list.sh
ls -1 /backups 2>/dev/null | while read -r d; do
  [ -d "/backups/$d" ] && printf '%s  %s\n' "$d" "$(du -sh "/backups/$d" | cut -f1)"
done
