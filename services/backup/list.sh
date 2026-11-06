#!/bin/sh
# Lists the backups with their size:  docker compose exec backup list.sh
for KIND in infrastructure application; do
  [ -d "/backups/$KIND" ] || continue
  echo "$KIND:"
  ls -1 "/backups/$KIND" 2>/dev/null | while read -r d; do
    [ -d "/backups/$KIND/$d" ] && printf '  %s  %s%s\n' "$d" "$(du -sh "/backups/$KIND/$d" | cut -f1)" "$([ -f "/backups/$KIND/$d/PINNED" ] && echo '  (pinned)')"
  done
done
