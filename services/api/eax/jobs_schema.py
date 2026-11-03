"""Create the Procrastinate tables in the "jobs" schema the first time (used by the entrypoint)."""

from __future__ import annotations

import sys

import psycopg

from .config import get_settings


def main() -> int:
    settings = get_settings()
    with psycopg.connect(settings.libpq_conninfo) as conn:
        exists = conn.execute("SELECT to_regclass('jobs.procrastinate_jobs')").fetchone()[0]
    if exists:
        print("EA Explorer: job queue schema already present")
        return 0
    from .jobs import app

    with app.open():
        app.schema_manager.apply_schema()
    print("EA Explorer: job queue schema created")
    return 0


if __name__ == "__main__":
    sys.exit(main())
