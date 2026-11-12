#!/bin/sh
# The Reports server (the reports service): the report content loads in the background (reports-content.sh, its output
# in this container's log), and the server starts at once (R2.39).
sh /app/eax/reports-content.sh 2>&1 | sed 's/^/[content] /' &

# Superset's own start script, wherever this image keeps it
for s in /usr/bin/run-server.sh /app/docker/entrypoints/run-server.sh; do
  if [ -x "$s" ]; then exec "$s"; fi
done
exec gunicorn --bind "0.0.0.0:${SUPERSET_PORT:-8088}" --workers "${SERVER_WORKER_AMOUNT:-1}" --worker-class gthread \
  --threads 20 --timeout "${GUNICORN_TIMEOUT:-60}" --limit-request-line 0 --limit-request-field_size 0 \
  "superset.app:create_app()"
