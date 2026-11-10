#!/bin/sh
# The views service: its database first (made when missing, then migrated), then the API.
set -eu
python -m viewsvc.bootstrap
exec gunicorn --bind 0.0.0.0:8110 --workers "${EAX_VIEWS_WORKERS:-2}" --threads 4 --timeout 120 \
  --access-logfile - "viewsvc.app:create_app()"
