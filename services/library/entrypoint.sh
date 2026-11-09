#!/bin/sh
# The library service: its database first (made when missing, then migrated), then the API.
set -eu
python -m libsvc.bootstrap
exec gunicorn --bind 0.0.0.0:8100 --workers "${EAX_LIBRARY_WORKERS:-2}" --threads 4 --timeout 120 \
  --access-logfile - "libsvc.app:create_app()"
