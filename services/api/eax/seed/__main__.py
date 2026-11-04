"""Loads the built-in models on start:  python -m eax.seed

Run by the api container's entrypoint after the database migrations. Each model is loaded once:
whatever is already present is left alone, so it is safe on every start.
  * ArchiMate 4 template (always)
  * Insurance reference model (always; a new version is a new model beside the old one)
  * Sample insurance model (when EAX_SEED_SAMPLE is true: the laptop template sets it)
  * Laptop only (with the sample): test models for roles (a fictitious insurer, Fynbos Mutual, from the
    insurance reference model, with Fynbos Life and Fynbos Commercial derived from it, and an
    independent Karoo Re), the test users' model assignments (phase 3.1), and a few saved versions of
    two sample entities for the History tab (D110)
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
from .build import GROUP_KEY, INSURANCE_ID, SAMPLE_ID, TEMPLATE_ID, gid, history_demo_steps, seed_sql, test_models_sql


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
        else:
            conn.execute(seed_sql(with_template=need["ArchiMate 4 template"],
                                  with_insurance=need["insurance reference model"],
                                  with_sample=need["sample model"]))
            counts = conn.execute(
                "SELECT (SELECT count(*) FROM core.models), (SELECT count(*) FROM core.entities)").fetchone()
            loaded = ", ".join(name for name, n in need.items() if n)
            print(f"EA Explorer: loaded the {loaded} ({counts[0]} models, {counts[1]} entities)")
        if settings.deployment == "laptop" and with_sample:
            if not conn.execute("SELECT 1 FROM core.models WHERE guid = %s", (gid("model", GROUP_KEY),)).fetchone():
                conn.execute(test_models_sql())
                print("EA Explorer: loaded the laptop test models (Fynbos Mutual group, Fynbos Life, Fynbos Commercial, Karoo Re)")
                history_demo(conn)
            assign_test_users(conn)
    return 0


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
