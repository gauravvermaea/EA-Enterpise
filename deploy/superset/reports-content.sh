#!/bin/sh
# The report content (R2.39): the report dashboards, the typed report datasets, the reader role and model access.
# Run by reports-start.sh in the background once the Reports server is starting, so Reports is up and usable while it
# loads; it runs again at every start (unchanged dashboards are skipped; phases 5 and 8.2).

# give the server a moment to start first
sleep 20

# The report dashboards (phases 5 and 8.2): all imported in one Superset process, one zip per dashboard so
# one failure does not stop the others; unchanged dashboards are skipped on later starts
echo "EA Explorer: importing the report dashboards (the first start takes a few minutes)"
python /app/eax/eax_import_reports.py

# the sample data loads after the API has started (D255): its typed report views are made as its models arrive, so the
# datasets wait for it (up to 30 minutes; then they are added with what is there, and the rest at the next start).
# Reports is already up meanwhile (before R2.39 this wait held Reports itself back, up to 15 minutes)
echo "EA Explorer: waiting for the sample data before adding the report datasets"
python - <<'PY' || true
import json, time, urllib.request
until = time.time() + 30 * 60
while time.time() < until:
    try:
        with urllib.request.urlopen("http://api:8000/api/startup", timeout=10) as r:
            later = next((p for p in json.load(r).get("parts", []) if p["key"] == "later"), None)
        if later is None or later["status"] in ("up", "down", "off"):
            print("EA Explorer: sample data", later["status"] if later else "not loading")
            break
    except Exception as exc:  # noqa: BLE001
        print("EA Explorer: the API is not answering yet:", exc)
    time.sleep(10)
PY

echo "EA Explorer: report datasets, the reader role and model access"
python /app/eax/eax_reports_init.py

echo "EA Explorer: report content ready"
