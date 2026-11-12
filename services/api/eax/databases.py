"""Every database EA Explorer uses, each with its own connection setting (R2.50, D611; owner, 12 Nov 2026: "Keep it in
same postgres DB, but ensure you have separate connection string for easy to migrate. We need a setting in config for
all the different DBs to have same or separate container").

Each database below has a setting in work/eaexplorer.env. Empty means the shared PostgreSQL server (the db container) as
today; filled in, it is a database of its own on another container or server. Moving one: dump it, restore it there,
set its setting, restart (docs/databases.md). Infrastructure backups dump each where it lives (services/backup/backup.sh)
and restores bring each back.

  python -m eax.databases          where each lives and whether it answers (eax databases)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class Db:
    key: str            # the name used in code and on the screens
    setting: str        # its setting in eaexplorer.env
    what: str           # what it holds
    kind: str = "url"   # url: a postgresql:// connection string; host: a host[:port] for a service's own database
    default: str = ""   # where it is when the setting is empty


DATABASES: tuple[Db, ...] = (
    Db("repository", "EAX_DB_HOST", "the architecture: models, metamodels, entities, relationships, views", "host", "db:5432/eaexplorer"),
    Db("changelog", "EAX_CHANGELOG_DB_URL", "the change log: every action, who, when, before and after (D180)", "url",
       "the repository's database, schema changelog"),
    Db("projects", "EAX_PROJECTS_DB_URL", "architecture projects, their steps, people and governance (D266)", "url",
       "the repository's database, schema proj"),
    Db("tests", "EAX_TESTS_DB_URL", "the self-test's runs, results and fixtures (R2.28)", "url", "the repository's database"),
    Db("operations", "EAX_OPERATIONS_DB_URL", "backups and schedules, deployments and updates, jobs, health history (R2.27)",
       "url", "the repository's database"),
    Db("personal", "EAX_PERSONAL_DB_URL", "each person's settings, profile and skills, notifications, drafts (R2.53)", "url",
       "the repository's database"),
    Db("library_models", "EAX_LIBRARY_MODELS_DB_URL", "the read-only shared models: industry and reference models (R2.42)",
       "url", "the repository's database"),
    Db("archive", "EAX_ARCHIVE_DB_URL", "archived and deleted models and projects (R2.41)", "url", "the repository's database"),
    Db("library", "EAX_LIBRARY_DB_HOST", "the reference and enterprise libraries' service", "host", "db:5432/eaxlibrary"),
    Db("views", "EAX_VIEWS_DB_HOST", "the views service", "host", "db:5432/eaxviews"),
    Db("keycloak", "EAX_KEYCLOAK_DB_HOST", "sign-in: Keycloak's users, roles and sessions", "host", "db:5432/keycloak"),
    Db("reports", "EAX_SUPERSET_DB_HOST", "Reports (Superset): its dashboards, charts and settings", "host", "db:5432/superset"),
    Db("documents", "EAX_MAYAN_DB_HOST", "Documents (Mayan): its index of the document files", "host", "db:5432/mayan"),
)
BY_KEY = {d.key: d for d in DATABASES}


def sqlalchemy_url(url: str) -> str:
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def setting(db: Db) -> str:
    return os.environ.get(db.setting, "").strip()


def own(db: Db) -> bool:
    """Whether it lives somewhere of its own (its setting points elsewhere than the shared server)."""
    v = setting(db)
    if not v:
        return False
    if db.kind == "host":
        return v.split(":")[0] not in ("db", "")
    shared = os.environ.get("EAX_DB_HOST", "db")
    parts = urlsplit(v)
    return not (parts.hostname in (shared, "db") and (parts.path or "").lstrip("/") == os.environ.get("EAX_DB_NAME", "eaexplorer"))


def where(db: Db) -> str:
    """Where it is, for people: the setting's host and database, never its password."""
    v = setting(db)
    if not v:
        return f"shared server ({db.default})"
    if db.kind == "host":
        return f"{v} ({'its own server' if own(db) else 'shared server'})"
    p = urlsplit(v)
    return f"{p.hostname}:{p.port or 5432}/{(p.path or '').lstrip('/')} ({'its own' if own(db) else 'shared server'})"


@lru_cache(maxsize=16)
def engine_for(key: str) -> Engine:
    """The engine of one of EA Explorer's own databases (kind url): its setting, or the repository's engine when empty,
    so code written against engine_for works the same whether the database was moved or not."""
    from .db import get_engine
    db = BY_KEY[key]
    if db.kind != "url" or not setting(db):
        return get_engine()
    return create_engine(sqlalchemy_url(setting(db)), pool_pre_ping=True, pool_size=2, max_overflow=4,
                         connect_args={"connect_timeout": 5, "application_name": f"eaexplorer-{key}"})


def status(check: bool = True) -> list[dict[str, Any]]:
    """Each database: what it holds, its setting, where it is, and (for EA Explorer's own) whether it answers."""
    out = []
    for db in DATABASES:
        row = {"key": db.key, "what": db.what, "setting": db.setting, "where": where(db), "own": own(db), "answers": None}
        if check and db.kind == "url":
            try:
                with engine_for(db.key).connect() as conn:
                    conn.execute(text("SELECT 1"))
                row["answers"] = True
            except Exception as exc:  # noqa: BLE001 - shown, not raised
                row["answers"], row["error"] = False, str(exc).splitlines()[0][:200]
        out.append(row)
    return out


def main(argv: list[str]) -> int:
    rows = status(check="--no-check" not in argv)
    print("EA Explorer's databases (R2.50): empty setting = the shared PostgreSQL; set one to move it (docs/databases.md)")
    for r in rows:
        ok = "" if r["answers"] is None else ("  answers" if r["answers"] else f"  DOES NOT ANSWER: {r.get('error', '')}")
        print(f"  {r['key']:<15}{r['where']:<52}{r['setting']}{ok}")
    return 0 if all(r["answers"] is not False for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
