"""Loads the built-in models on start:  python -m eax.seed

Run by the api container's entrypoint after the database migrations, before the API starts: only what everyone
needs to sign in and work (the core of the start-up, D255). Each model is loaded once: whatever is already present is
left alone, so it is safe on every start.
  * ArchiMate 4 template (always)
  * Insurance reference model (always; a new version is a new model beside the old one)
  * The built-in viewpoints and report audiences (always, phase 8.2)
  * The project library (always, phase 13): phases, steps, deliverables and artifacts, folders, templates; on a laptop
    with the sample, a sample principles library
  * Laptop only: the test users' roles on the models present
The sample insurance model, the laptop test models, the demo estate and the first data quality measurement are loaded
after the API has started, in the background, one step at a time (eax/seed/later.py), so the start is not held up.
Templates and reference models are locked, so this runs as the installer's login (eax_migrator,
EAX_DB_MIGRATOR_PASSWORD), the only login the database lets change them.
"""

from __future__ import annotations

import os
import sys
import time

import psycopg

from ..config import get_settings
from ..permissions import TEST_USERS
from . import project_library
from .build import INSURANCE_ID, TEMPLATE_ID, history_demo_steps, seed_sql
from .catalog import catalog_sql


def main() -> int:
    settings = get_settings()
    if not settings.db_migrator_password:
        print("EA Explorer seed: EAX_DB_MIGRATOR_PASSWORD is not set; built-in models not loaded", file=sys.stderr)
        return 1
    with psycopg.connect(settings.migrator_conninfo) as conn:
        present = {str(r[0]) for r in conn.execute(
            "SELECT guid FROM core.models WHERE guid IN (%s, %s)", (TEMPLATE_ID, INSURANCE_ID)).fetchall()}
        need = {"ArchiMate 4 template": TEMPLATE_ID not in present, "insurance reference model": INSURANCE_ID not in present}
        if not any(need.values()):
            print("EA Explorer: built-in models already present")
        else:
            conn.execute(seed_sql(with_template=need["ArchiMate 4 template"],
                                  with_insurance=need["insurance reference model"], with_sample=False))
            loaded = ", ".join(name for name, n in need.items() if n)
            print(f"EA Explorer: loaded the {loaded}")
        if settings.deployment == "laptop":
            assign_test_users(conn)
        give_icons(conn)
        # the built-in viewpoints and report audiences follow eax/report_defs.py (phase 8.2, D161)
        conn.execute(catalog_sql())
        print("EA Explorer: viewpoints and report audiences brought up to date")
        refresh_views(conn)
    # the project library: phases, steps, deliverables and artifacts, folders, template libraries (phase 13, D258, D264),
    # in the projects' database (EAX_PROJECTS_DB_URL when proj has been moved to its own, D266)
    with (psycopg.connect(settings.projects_db_url) if settings.projects_db_url else psycopg.connect(settings.migrator_conninfo)) as pconn:
        pconn.execute(project_library.library_sql())
        if os.environ.get("EAX_SEED_SAMPLE", "false").strip().lower() in ("1", "true", "yes"):
            pconn.execute(project_library.sample_principles_sql())
    print("EA Explorer: project library brought up to date")
    return 0


def give_icons(conn) -> None:
    """Every model has an icon (D247): those without one get their kind's."""
    conn.execute("""INSERT INTO core.model_icons (model_id, library, set_by)
                    SELECT m.id, CASE m.kind_code WHEN 'template' THEN 'layers' WHEN 'reference' THEN 'bank' ELSE 'building' END,
                           'eax_migrator'
                      FROM core.models m WHERE NOT m.is_deleted
                       AND NOT EXISTS (SELECT 1 FROM core.model_icons i WHERE i.model_id = m.id)""")


def refresh_views(conn) -> None:
    """The typed report views (rpt.t_*) follow the metamodels loaded (D139)."""
    n = conn.execute("SELECT rpt.refresh_typed_views()").fetchone()[0]
    print(f"EA Explorer: report views brought up to date ({n} changed)")


def history_demo(conn) -> None:
    """Laptop only: saves a few versions of two sample entities (Customer Portal, Policy Administration
    System), each step by a test user in its own transaction a moment apart, so their History tabs show
    values set, changed and cleared and relationships added and removed (D110)."""
    conn.commit()
    steps = history_demo_steps()
    for i, (_actor, sql) in enumerate(steps):
        if i:
            time.sleep(1.5)   # a separate moment on the timeline (moments are one person within one second)
        conn.execute(sql)
        conn.commit()
    print(f"EA Explorer: saved {len(steps)} versions of the sample Customer Portal for the History tab")


def assign_test_users(conn) -> None:
    """Laptop only: the test users' roles on models (phase 3.1): named models, or every model ("*")."""
    n = 0
    for username, _role, models in TEST_USERS:
        for model, roles in models.items():
            for role in roles:
                where, args = ("true", (username, role)) if model == "*" else ("name = %s", (username, role, model))
                n += conn.execute(f"""INSERT INTO core.model_users (model_id, username, role, created_by)
                                      SELECT id, %s, %s, 'system:seed' FROM core.models WHERE {where}
                                      ON CONFLICT (model_id, username, role) DO NOTHING""", args).rowcount
    if n:
        print(f"EA Explorer: gave the laptop test users their model roles ({n})")


if __name__ == "__main__":
    sys.exit(main())
