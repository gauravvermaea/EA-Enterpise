"""Imports the EA Explorer report dashboards into Superset in one process (phase 8.2).

Phase 5 ran `superset import-dashboards` once per dashboard. Each run starts the whole of Superset again
(10 to 20 seconds), which was fine for 32 dashboards and far too slow for 111. This script starts Superset
once and imports every zip in /rendered/superset/reports with the same command the CLI uses, one dashboard at
a time, so one that fails does not stop the others. A dashboard whose zip has not changed since the last
import (same SHA-256, kept in superset_home) and still in Superset is skipped, so later starts are quick.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from zipfile import ZipFile

REPORTS = Path("/rendered/superset/reports")
STAMPS = Path("/app/superset_home/eax-report-imports.json")


def _contents(bundle: ZipFile) -> dict[str, str]:
    try:   # what `superset import-dashboards` reads (the zip's top folder removed)
        from superset.commands.importers.v1.utils import get_contents_from_bundle
        return get_contents_from_bundle(bundle)
    except ImportError:
        return {name.split("/", 1)[1] if "/" in name else name: bundle.read(name).decode("utf-8")
                for name in bundle.namelist() if not name.endswith("/")}


def main() -> int:
    zips = sorted(REPORTS.glob("*.zip")) if REPORTS.is_dir() else []
    if not zips:
        print("EA Explorer: no report dashboards to import")
        return 0
    from flask import g

    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset import db
        from superset import security_manager as sm
        try:
            from superset.commands.dashboard.importers.dispatcher import ImportDashboardsCommand
        except ImportError:   # Superset before 4.0
            from superset.dashboards.commands.importers.dispatcher import ImportDashboardsCommand

        from superset.models.dashboard import Dashboard

        g.user = sm.find_user(username="admin")
        have = {d.slug for d in db.session.query(Dashboard.slug).all()}
        try:
            stamps = json.loads(STAMPS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stamps = {}
        done = skipped = failed = 0
        started = time.monotonic()
        for i, z in enumerate(zips, 1):
            digest = hashlib.sha256(z.read_bytes()).hexdigest()
            if stamps.get(z.name) == digest and z.stem in have:   # unchanged and still there
                skipped += 1
                continue
            try:
                with ZipFile(z) as bundle:
                    ImportDashboardsCommand(_contents(bundle), overwrite=True).run()
                stamps[z.name] = digest
                done += 1
                print(f"EA Explorer: imported report {z.stem} ({i} of {len(zips)})", flush=True)
            except Exception as exc:  # noqa: BLE001 - one failure must not stop the others
                db.session.rollback()
                stamps.pop(z.name, None)
                failed += 1
                print(f"EA Explorer WARNING: report {z.stem} failed to import ({exc}); the other reports still work", flush=True)
        for gone in set(stamps) - {z.name for z in zips}:
            stamps.pop(gone, None)
        try:
            STAMPS.write_text(json.dumps(stamps, indent=1), encoding="utf-8")
        except OSError as exc:
            print(f"EA Explorer WARNING: could not keep the import stamps ({exc}); every report is imported again next start")
        print(f"EA Explorer: report dashboards imported: {done} new or changed, {skipped} unchanged, {failed} failed "
              f"({time.monotonic() - started:.0f} s)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - Superset still works without the reports
        print(f"EA Explorer WARNING: importing the report dashboards failed: {exc}")
        sys.exit(0)
