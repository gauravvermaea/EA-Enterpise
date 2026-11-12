#!/bin/sh
# One-shot Superset initialisation (the reports-init service): only what the Reports server needs before it starts:
#   metadata database, break-glass admin, roles and permissions, the phase 0 sample dashboard.
# The report dashboards, the typed datasets, the reader role and model access (the content) load after the server has
# started, in the background, from reports-start.sh (R2.39, owner, 12 Nov 2026: "why report is taking so long, can
# content load not run after up of report?": Reports waited for all of it, many minutes, while the sample data loaded).
set -e

echo "EA Explorer: Superset database upgrade"
superset db upgrade

echo "EA Explorer: Superset break-glass admin (normal sign-in is through Keycloak)"
superset fab create-admin \
  --username admin --firstname Superset --lastname Admin \
  --email "superset-admin@example.org" \
  --password "${EAX_SUPERSET_ADMIN_PASSWORD}" || true

# Older installs gave the break-glass admin the first user's email, which blocks that user's
# Keycloak sign-in (Superset emails are unique). Move it out of the way if so.
python - <<'PY' || true
import os
from superset.app import create_app
app = create_app()
with app.app_context():
    from superset import security_manager as sm
    user = sm.find_user(username="admin")
    first = os.environ.get("EAX_FIRST_ADMIN_EMAIL", "")
    if user and first and user.email == first:
        user.email = "superset-admin@example.org"
        sm.update_user(user)
        print("EA Explorer: break-glass admin email changed to superset-admin@example.org")
PY

echo "EA Explorer: Superset roles and permissions"
superset init

if [ -f /rendered/superset/sample_dashboard.zip ]; then
  echo "EA Explorer: importing the phase 0 sample dashboard"
  superset import-dashboards -p /rendered/superset/sample_dashboard.zip -u admin \
    || echo "EA Explorer WARNING: sample dashboard import failed; Superset still works (see docs/phase-0.md)"
fi

echo "EA Explorer: Superset set up (the report content loads once Reports has started)"
