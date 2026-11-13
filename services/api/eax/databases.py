"""Every database EA Explorer uses, each with its own connection setting (R2.50, D611; owner, 12 Nov 2026: "Keep it in
same postgres DB, but ensure you have separate connection string for easy to migrate. We need a setting in config for
all the different DBs to have same or separate container").

Each database below has a setting in work/eaexplorer.env. Empty means the shared PostgreSQL server (the db container) as
today; filled in, it is a database of its own on another container or server. Moving one: dump it, restore it there,
set its setting, restart (docs/databases.md). Infrastructure backups dump each where it lives (services/backup/backup.sh)
and restores bring each back.

  python -m eax.databases          where each lives and whether it answers (eax databases)
  python -m eax.databases ensure   the tables of each database of its own made or brought in line (at every start)
  python -m eax.databases copy KEY the rows of a database moved to its own server copied there from the shared one

The migrations (alembic) keep every table in the shared database, so they stay the one description of each table: a
database of its own gets its tables copied from there, column by column, constraint by constraint and index by index
(ensure, R2.28, D613), and the shared copies are left empty and unused.
"""

from __future__ import annotations

import json
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

# the tables each of EA Explorer's own databases holds, in the order they are made (a table before those that refer to it)
TABLES: dict[str, tuple[str, ...]] = {
    "tests": ("core.test_runs", "core.test_results", "core.test_fixtures"),
}


def sqlalchemy_url(url: str) -> str:
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def setting(db: Db) -> str:
    return os.environ.get(db.setting, "").strip()


def own(db: Db) -> bool:
    """Whether it lives somewhere of its own (its setting points elsewhere than the shared server)."""
    if db.key == "repository":
        return False
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
    if db.key == "repository":                       # the shared server itself
        return f"{v or 'db'}:{os.environ.get('EAX_DB_PORT', '5432')}/{os.environ.get('EAX_DB_NAME', 'eaexplorer')} (the shared server)"
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


# ---------------------------------------------------------------- a database of its own: its tables (R2.28, D613)
_COLUMNS = """SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, pg_get_expr(d.adbin, d.adrelid),
                     a.attidentity
                FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
               WHERE a.attrelid = to_regclass(:t) AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum"""
_CONSTRAINTS = """SELECT conname, pg_get_constraintdef(oid), contype FROM pg_constraint
                   WHERE conrelid = to_regclass(:t) ORDER BY CASE contype WHEN 'p' THEN 0 WHEN 'u' THEN 1 WHEN 'c' THEN 2
                                                                         ELSE 3 END, conname"""
_INDEXES = """SELECT i.relname, pg_get_indexdef(i.oid) FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
               WHERE x.indrelid = to_regclass(:t)
                 AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.oid) ORDER BY i.relname"""


def _column_sql(name: str, typ: str, notnull: bool, default: str | None, identity: str) -> str:
    out = f'"{name}" {typ}'
    if identity in ("a", "d"):
        out += f" GENERATED {'ALWAYS' if identity == 'a' else 'BY DEFAULT'} AS IDENTITY"
    elif default is not None:
        out += f" DEFAULT {default}"
    return out + (" NOT NULL" if notnull else "")


def plan(shared, own_conn, tables: tuple[str, ...]) -> list[str]:
    """The statements that bring the tables in own_conn in line with the shared database's (the migrations' result):
    the schema, each missing table and column, each constraint and index added or replaced when it differs, those no
    longer in the shared database dropped. Nothing is dropped from a table but constraints and indexes (D248)."""
    out: list[str] = []
    for schema in sorted({t.split(".")[0] for t in tables}):
        out.append(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    fks: list[str] = []
    for t in tables:
        cols = [tuple(r) for r in shared.execute(text(_COLUMNS), {"t": t}).all()]
        if not cols:
            raise LookupError(f"{t} is not in the shared database: run the migrations first (eax up).")
        have = {r[0] for r in own_conn.execute(text(_COLUMNS), {"t": t}).all()}
        if not have:
            out.append(f"CREATE TABLE {t} (" + ", ".join(_column_sql(*c) for c in cols) + ")")
        else:
            out += [f"ALTER TABLE {t} ADD COLUMN {_column_sql(*c)}" for c in cols if c[0] not in have]
        want = {n: (d, k) for n, d, k in shared.execute(text(_CONSTRAINTS), {"t": t}).all()}
        got = {n: d for n, d, _k in own_conn.execute(text(_CONSTRAINTS), {"t": t}).all()} if have else {}
        for n in got:
            if n not in want or got[n] != want[n][0]:
                out.append(f'ALTER TABLE {t} DROP CONSTRAINT "{n}"')
        for n, (d, k) in want.items():
            if got.get(n) != d:
                (fks if k == "f" else out).append(f'ALTER TABLE {t} ADD CONSTRAINT "{n}" {d}')
        iwant = dict(shared.execute(text(_INDEXES), {"t": t}).all())
        igot = dict(own_conn.execute(text(_INDEXES), {"t": t}).all()) if have else {}
        schema = t.split(".")[0]
        for n, d in igot.items():
            if iwant.get(n) != d:
                out.append(f'DROP INDEX {schema}."{n}"')
        out += [d for n, d in iwant.items() if igot.get(n) != d]
    return out + fks                                 # foreign keys last: every table they refer to is there


def ensure(say=print) -> int:
    """Every database of its own with tables of EA Explorer's (TABLES): made or brought in line with the shared one."""
    from .db import get_engine
    done = 0
    for key, tables in TABLES.items():
        db = BY_KEY[key]
        if not own(db):
            continue
        with get_engine().connect() as shared, engine_for(key).begin() as conn:
            steps = plan(shared, conn, tables)
            for sql in steps:
                conn.execute(text(sql))
        say(f"{key}: {len(steps)} change(s) at {where(db)}" if len(steps) > 1 else f"{key}: in line at {where(db)}")
        done += 1
    return done


def copy(key: str, say=print) -> dict[str, int]:
    """The rows of a database moved to its own server, copied from the shared database (for runs made before it moved):
    rows already there (by id) are kept; each table's id counter carries on after the highest id."""
    from .db import get_engine
    db = BY_KEY.get(key)
    if not db or key not in TABLES:
        raise ValueError(f"Copy works for: {', '.join(TABLES)}.")
    if not own(db):
        raise ValueError(f"{key} is in the shared database: set {db.setting} first (docs/databases.md).")
    ensure(say=lambda _m: None)
    out: dict[str, int] = {}
    with get_engine().connect() as shared, engine_for(key).begin() as conn:
        for t in TABLES[key]:
            cols = [c[0] for c in shared.execute(text(_COLUMNS), {"t": t}).all()]
            names = ", ".join(f'"{c}"' for c in cols)
            have = {r[0] for r in conn.execute(text(f"SELECT id FROM {t}")).all()}   # noqa: S608 - fixed names
            rows = [r for r in shared.execute(text(f"SELECT {names} FROM {t} ORDER BY id")).mappings().all()   # noqa: S608
                    if r["id"] not in have]
            for r in rows:
                conn.execute(text(f"INSERT INTO {t} ({names}) OVERRIDING SYSTEM VALUE VALUES ("   # noqa: S608
                                  + ", ".join(f":{c}" for c in cols) + ")"),
                             {c: (json.dumps(r[c]) if isinstance(r[c], dict | list) and not isinstance(r[c], str)
                                  and c not in ("suites", "journeys") else r[c]) for c in cols})
            conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                              f"GREATEST((SELECT max(id) FROM {t}), 1))"))
            out[t] = len(rows)
            say(f"{t}: {len(rows)} row(s) copied")
    return out


def main(argv: list[str]) -> int:
    if argv[:1] == ["ensure"]:
        ensure()
        return 0
    if argv[:1] == ["copy"]:
        try:
            copy(argv[1] if len(argv) > 1 else "")
        except (ValueError, LookupError) as exc:
            print(exc)
            return 2
        print("Copied. The shared database's rows stay as they were (empty them with SQL when you are sure).")
        return 0
    rows = status(check="--no-check" not in argv)
    print("EA Explorer's databases (R2.50): empty setting = the shared PostgreSQL; set one to move it (docs/databases.md)")
    for r in rows:
        ok = "" if r["answers"] is None else ("  answers" if r["answers"] else f"  DOES NOT ANSWER: {r.get('error', '')}")
        print(f"  {r['key']:<15}{r['where']:<62}{r['setting']}{ok}")
    return 0 if all(r["answers"] is not False for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
