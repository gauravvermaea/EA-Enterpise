"""Loads the built-in models on start:  python -m eax.seed

Run by the api container's entrypoint after the database migrations. Each model is loaded once:
whatever is already present is left alone, so it is safe on every start.
  * ArchiMate 4 template (always)
  * Insurance reference model (always; a new version is a new model beside the old one)
  * Sample insurance model (when EAX_SEED_SAMPLE is true: the laptop template sets it)
Templates and reference models are locked, so this runs as the installer's login (eax_migrator,
EAX_DB_MIGRATOR_PASSWORD), the only login the database lets change them.
"""

from __future__ import annotations

import os
import sys

import psycopg

from ..config import get_settings
from .build import INSURANCE_ID, SAMPLE_ID, TEMPLATE_ID, seed_sql


def main() -> int:
    settings = get_settings()
    if not settings.db_migrator_password:
        print("EA Explorer seed: EAX_DB_MIGRATOR_PASSWORD is not set; built-in models not loaded", file=sys.stderr)
        return 1
    with_sample = os.environ.get("EAX_SEED_SAMPLE", "false").strip().lower() in ("1", "true", "yes")
    with psycopg.connect(settings.migrator_conninfo) as conn:
        present = {str(r[0]) for r in conn.execute(
            "SELECT guid FROM core.models WHERE guid IN (%s, %s, %s)",
            (TEMPLATE_ID, INSURANCE_ID, SAMPLE_ID)).fetchall()}
        need = {
            "ArchiMate 4 template": TEMPLATE_ID not in present,
            "insurance reference model": INSURANCE_ID not in present,
            "sample model": with_sample and SAMPLE_ID not in present,
        }
        if not any(need.values()):
            print("EA Explorer: built-in models already present")
            return 0
        conn.execute(seed_sql(with_template=need["ArchiMate 4 template"],
                              with_insurance=need["insurance reference model"],
                              with_sample=need["sample model"]))
        counts = conn.execute(
            "SELECT (SELECT count(*) FROM core.models), (SELECT count(*) FROM core.entities)").fetchone()
    loaded = ", ".join(name for name, n in need.items() if n)
    print(f"EA Explorer: loaded the {loaded} ({counts[0]} models, {counts[1]} entities)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
