"""Loads the ArchiMate 4 starter metamodel on first start:  python -m eax.seed

Run by the api container's entrypoint after the database migrations. It does nothing when the
template model already exists, so it is safe on every start. The sample model is added when
EAX_SEED_SAMPLE is true (the laptop template sets it; the server template does not).
"""

from __future__ import annotations

import os
import sys

import psycopg

from ..config import get_settings
from .build import SAMPLE_ID, TEMPLATE_ID, seed_sql


def main() -> int:
    with_sample = os.environ.get("EAX_SEED_SAMPLE", "false").strip().lower() in ("1", "true", "yes")
    with psycopg.connect(get_settings().libpq_conninfo) as conn:
        present = {str(r[0]) for r in conn.execute(
            "SELECT guid FROM core.model WHERE guid IN (%s, %s)", (TEMPLATE_ID, SAMPLE_ID)).fetchall()}
        need_template = TEMPLATE_ID not in present
        need_sample = with_sample and SAMPLE_ID not in present
        if not need_template and not need_sample:
            print("EA Explorer: ArchiMate 4 seed already present")
            return 0
        conn.execute(seed_sql(with_template=need_template, with_sample=need_sample))
        counts = conn.execute(
            "SELECT (SELECT count(*) FROM core.model), (SELECT count(*) FROM core.entity)"
        ).fetchone()
    loaded = " and ".join(x for x, n in (("ArchiMate 4 template", need_template),
                                          ("sample model", need_sample)) if n)
    print(f"EA Explorer: loaded the {loaded} ({counts[0]} models, {counts[1]} entities)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
