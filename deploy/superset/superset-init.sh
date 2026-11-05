#!/bin/sh
# One-shot Superset initialisation (the reports-init service):
#   metadata database, roles, break-glass admin, the phase 0 sample dashboard, the standard reports
#   (phase 5), typed report datasets, the reader role and model access (eax_reports_init.py).
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
# The report dashboards (phases 5 and 8.2): all imported in one Superset process, one zip per dashboard so
# one failure does not stop the others; unchanged dashboards are skipped on later starts
echo "EA Explorer: importing the report dashboards (the first start takes a few minutes)"
python /app/eax/eax_import_reports.py

echo "EA Explorer: report datasets, the reader role and model access"
python /app/eax/eax_reports_init.py

echo "EA Explorer: Superset ready"
