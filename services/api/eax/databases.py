"""Every database EA Explorer uses, each with its own connection setting (R2.50, D611), and the parts of the repository
database that can move, each a SCHEMA of its own (D630; owner, 13 Nov 2026, 08:43: "it can be in a seperate schema on
same DB Server and database ... having many database instance server container will take a lot of memory ... when we
want to scale out all we change is the location"; 08:45: "only limited to schemas no new DB server or DB is created").

  tests           tests.*            the self-test's runs, results, fixtures (R2.28)       EAX_TESTS_DB_URL
  operations      operations.*       backups, deployments, updates, health (R2.27)         EAX_OPERATIONS_DB_URL
  archive         archive.*          archived and deleted models and projects (R2.41)      EAX_ARCHIVE_DB_URL
  personal        personal.*         each person's notifications, requests ... (R2.53)     EAX_PERSONAL_DB_URL
  library_models  library_models.*   the read-only shared models (R2.42)                    EAX_LIBRARY_MODELS_DB_URL
  files           files.*            files on a platform with no local file system (R2.44)  EAX_FILES_DB_URL
  farm            farm.*             the EA Explorer sites in the site picker (R2.1)        EAX_FARM_DB_URL

By default each setting is empty and its schema is in the one repository database (the migrations make it there): one
PostgreSQL, one database, one connection pool. Scaling one out: point its setting at another PostgreSQL database that
already exists (EA Explorer never creates a database or a server), restart; at start `ensure` makes the schema and its
tables there from the migrations' description, and `copy KEY` brings the rows already here. Code always names a table
with its schema (tests.test_runs), so nothing else changes when one moves.

  python -m eax.databases          where each lives and whether it answers (eax databases)
  python -m eax.databases ensure   the schema and tables of each one moved elsewhere made or brought in line (each start)
  python -m eax.databases speed    how fast text is compared (R2.52)
  python -m eax.databases copy KEY the rows of one moved elsewhere copied there from the repository database
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
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
    Db("tests", "EAX_TESTS_DB_URL", "the self-test's runs, results and fixtures (R2.28)", "url", "schema tests in the repository's database"),
    Db("operations", "EAX_OPERATIONS_DB_URL", "backups and schedules, deployments and updates, jobs, health history (R2.27)",
       "url", "schema operations in the repository's database"),
    Db("personal", "EAX_PERSONAL_DB_URL", "each person's settings, profile and skills, notifications, drafts (R2.53)", "url",
       "schema personal in the repository's database"),
    Db("library_models", "EAX_LIBRARY_MODELS_DB_URL", "the read-only shared models: industry and reference models (R2.42)",
       "url", "schema library_models in the repository's database"),
    Db("files", "EAX_FILES_DB_URL", "files on a platform with no local file system: self-test reports, exports (R2.44)", "url",
       "schema files in the repository's database"),
    Db("farm", "EAX_FARM_DB_URL", "the EA Explorer sites everyone sees in the site picker (R2.1)", "url",
       "schema farm in the repository's database"),
    Db("archive", "EAX_ARCHIVE_DB_URL", "archived and deleted models and projects (R2.41)", "url", "schema archive in the repository's database"),
    Db("library", "EAX_LIBRARY_DB_HOST", "the reference and enterprise libraries' service", "host", "db:5432/eaxlibrary"),
    Db("views", "EAX_VIEWS_DB_HOST", "the views service", "host", "db:5432/eaxviews"),
    Db("keycloak", "EAX_KEYCLOAK_DB_HOST", "sign-in: Keycloak's users, roles and sessions", "host", "db:5432/keycloak"),
    Db("reports", "EAX_SUPERSET_DB_HOST", "Reports (Superset): its dashboards, charts and settings", "host", "db:5432/superset"),
    Db("documents", "EAX_MAYAN_DB_HOST", "Documents (Mayan): its index of the document files", "host", "db:5432/mayan"),
)
BY_KEY = {d.key: d for d in DATABASES}

# the tables each of EA Explorer's own databases holds, in the order they are made (a table before those that refer to it)
TABLES: dict[str, tuple[str, ...]] = {
    "tests": ("tests.test_runs", "tests.test_results", "tests.test_fixtures"),
    # the running of the installation (R2.27, owner 12 Nov 2026): backup schedules, deployments, updates and installed
    # versions, the start-up status, health history; housekeeping stays (it moves the model's own rows)
    "archive": ("archive.archive_store",),                 # archived and deleted models and projects (R2.41)
    "operations": ("operations.backup_schedules", "operations.deployments", "operations.update_history",
                   "operations.heartbeat_logs", "operations.startup_parts", "operations.ssh_sessions"),
    "files": ("files.store",),                          # EAX_FILE_STORE=database (R2.44, D635)
    "farm": ("farm.sites",),                            # the sites (R2.1, D646)
    # each person's own data (R2.53, D632): no foreign key into the repository
    # the library models' content (R2.42, D633): the model rows stay in core.models
    "library_models": tuple(f"library_models.{t}" for t in (
        "layers", "pick_lists", "pick_list_values", "attribute_types", "entity_types", "relationship_types", "item_attributes",
        "allowed_relationships", "item_attribute_mappings", "validation_rules", "metamodel_versions", "metamodel_version_changes",
        "display_id_counters", "model_icons", "entities", "entity_aliases", "entity_icons", "attribute_values", "relationships",
        "row_versions")),
    "personal": ("personal.notifications", "personal.notification_recipients", "personal.requests", "personal.request_comments",
                 "personal.favourites", "personal.saved_views", "personal.user_skills", "personal.settings",
                 "personal.remote_instances"),
}
# the schema of each part that can move (D630): the same name wherever it lives
SCHEMAS: dict[str, str] = {"tests": "tests", "operations": "operations", "archive": "archive", "personal": "personal",
                           "library_models": "library_models", "files": "files",
                           "farm": "farm"}


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
    from .db import base_engine
    db = BY_KEY[key]
    if db.kind != "url" or not setting(db):
        return base_engine()
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


@contextmanager
def beside(key: str, conn) -> Iterator[Any]:
    """The tables of one of EA Explorer's own databases (TABLES[key]) beside a repository connection: conn itself when
    they share the database (one transaction, as before), else a transaction of that database, committed at the end."""
    if not own(BY_KEY[key]):
        yield conn
        return
    with engine_for(key).begin() as c:
        yield c


class _Done:
    """What a statement that returns no rows answers on a database of its own: its row count."""
    def __init__(self, rowcount: int):
        self.rowcount = rowcount

    def scalar(self):
        return None

    def first(self):
        return None


class _Apart:
    """A database of its own, used like a connection for one statement at a time: each runs in its own transaction and
    its rows are read before it ends (Result.freeze), so callers use the answer as they would a connection's."""
    def __init__(self, key: str):
        self.key = key

    def execute(self, stmt, params=None):
        with engine_for(self.key).begin() as c:
            r = c.execute(stmt, params or {})
            return r.freeze()() if r.returns_rows else _Done(r.rowcount)


def on(key: str, conn):
    """Where to run a statement on one of TABLES[key]: conn itself when the database is the shared one (the same
    transaction as the rest, as before), else that database (one statement, one transaction)."""
    return _Apart(key) if own(BY_KEY[key]) else conn


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
    if default and re.search(r"\b(core|history|eax|proj)\.\w+\(", default):
        default = None        # a default that calls the repository's functions: the application sets the value there
    out = f'"{name}" {typ}'
    if identity in ("a", "d"):
        out += f" GENERATED {'ALWAYS' if identity == 'a' else 'BY DEFAULT'} AS IDENTITY"
    elif default is not None:
        out += f" DEFAULT {default}"
    return out + (" NOT NULL" if notnull else "")


def plan(shared, own_conn, tables: tuple[str, ...], with_fks: bool = True) -> list[str]:
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
        serial = [(c[0], m.group(1)) for c in cols if c[0] not in have and c[3]
                  and (m := re.match(r"nextval\('([^']+)'::regclass\)", c[3]))]
        out += [f"CREATE SEQUENCE IF NOT EXISTS {q}" for _c, q in serial]     # a serial column's counter first
        if not have:
            out.append(f"CREATE TABLE {t} (" + ", ".join(_column_sql(*c) for c in cols) + ")")
        else:
            out += [f"ALTER TABLE {t} ADD COLUMN {_column_sql(*c)}" for c in cols if c[0] not in have]
        out += [f"ALTER SEQUENCE {q} OWNED BY {t}.\"{c}\"" for c, q in serial]
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
    # foreign keys last: every table they refer to is there (a copy of the directory, D633, keeps none)
    return out + (fks if with_fks else [])


# the repository's directory tables a library model's screens join (R2.42, D633): copied beside the library_models
# schema when it lives in a database of its own, as plain tables (no foreign keys), and kept current (sync_directory)
DIRECTORY = ("core.model_kinds", "core.item_statuses", "core.data_types", "core.rule_types", "core.models", "core.model_tags",
             "core.model_users", "core.known_users", "core.commits", "core.pending_changes", "core.change_sets",
             "core.model_publish_events", "core.metamodel_drafts", "core.quality_settings", "core.quality_rules",
             "core.quality_defaults", "core.quality_exemptions", "core.quality_scope")


def _run_all(conn, steps: list[str], say) -> int:
    """Each statement in a savepoint: an index the target cannot make (an extension it lacks, such as pg_trgm for a
    contains search) is left out with a warning; anything else stops the start."""
    done = 0
    for sql in steps:
        sp = conn.begin_nested()
        try:
            conn.execute(text(sql))
            sp.commit()
            done += 1
        except Exception as exc:  # noqa: BLE001 - decided below
            sp.rollback()
            if sql.lstrip().upper().startswith("CREATE INDEX") or sql.lstrip().upper().startswith("CREATE UNIQUE INDEX"):
                say(f"  left out (the target cannot make it): {sql[:120]}: {str(exc).splitlines()[0][:120]}")
                continue
            raise
    return done


def ensure(say=print) -> int:
    """Every database of its own with tables of EA Explorer's (TABLES): made or brought in line with the shared one."""
    from .db import base_engine
    done = 0
    for key, tables in TABLES.items():
        db = BY_KEY[key]
        if not own(db):
            continue
        with base_engine().connect() as shared, engine_for(key).begin() as conn:
            if key == "library_models":
                try:
                    with conn.begin_nested():
                        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                except Exception:  # noqa: BLE001 - its contains-search indexes are left out then
                    pass
                _run_all(conn, plan(shared, conn, DIRECTORY, with_fks=False), say)
            steps = plan(shared, conn, tables)
            _run_all(conn, steps, say)
        if key == "library_models":
            sync_directory()
        say(f"{key}: {len(steps)} change(s) at {where(db)}" if len(steps) > 1 else f"{key}: in line at {where(db)}")
        done += 1
    return done


def sync_directory() -> int:
    """The directory tables copied to the library_models database of its own (D633): all their rows, replaced, in one
    transaction. Nothing to do while library_models is in the repository's database."""
    from .db import base_engine
    if not own(BY_KEY["library_models"]):
        return 0
    n = 0
    with base_engine().connect() as shared, engine_for("library_models").begin() as conn:
        for t in reversed(DIRECTORY):
            conn.execute(text(f"DELETE FROM {t}"))                    # noqa: S608 - fixed names
        for t in DIRECTORY:
            there = {c[0] for c in conn.execute(text(_COLUMNS), {"t": t}).all()}   # a column added later (is_test_data)
            info = [c for c in shared.execute(text(_COLUMNS), {"t": t}).all() if c[0] in there]
            cols = [c[0] for c in info]
            ident = any(c[4] in ("a", "d") for c in info)
            jsonish = {c[0]: "json" in str(c[1]) for c in info}
            names = ", ".join(f'"{c}"' for c in cols)
            only = (" WHERE model_id IN (SELECT id FROM core.models WHERE content_schema = 'library_models')"
                    if "model_id" in cols and t != "core.models" else "")     # a model's rows: the library models' only
            rows = shared.execute(text(f"SELECT {names} FROM {t}{only}")).mappings().all()   # noqa: S608
            for r in rows:
                conn.execute(text(f"INSERT INTO {t} ({names}) {'OVERRIDING SYSTEM VALUE ' if ident else ''}VALUES ("  # noqa: S608
                                  + ", ".join(f":{c}" for c in cols) + ")"),
                             {c: (json.dumps(r[c]) if jsonish[c] and isinstance(r[c], (dict, list)) else r[c]) for c in cols})
            n += len(rows)
    return n


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
            there = {c[0] for c in conn.execute(text(_COLUMNS), {"t": t}).all()}   # a column added later (is_test_data)
            info = [c for c in shared.execute(text(_COLUMNS), {"t": t}).all() if c[0] in there]
            cols = [c[0] for c in info]
            jsonish = {c[0]: "json" in str(c[1]) for c in info}
            ident = [c[0] for c in info if c[4] in ("a", "d")]
            counted = ident + [c[0] for c in info if c[3] and str(c[3]).startswith("nextval(")]
            pk = shared.execute(text("""SELECT a.attname FROM pg_index x JOIN pg_attribute a ON a.attrelid = x.indrelid
                                         AND a.attnum = ANY(x.indkey) WHERE x.indrelid = to_regclass(:t) AND x.indisprimary"""),
                                {"t": t}).scalars().all()
            names = ", ".join(f'"{c}"' for c in cols)
            keyed = ", ".join(f'"{c}"' for c in pk)
            have = {tuple(r) for r in conn.execute(text(f"SELECT {keyed} FROM {t}")).all()}   # noqa: S608 - fixed names
            rows = [r for r in shared.execute(text(f"SELECT {names} FROM {t} ORDER BY {keyed}")).mappings().all()   # noqa: S608
                    if tuple(r[c] for c in pk) not in have]
            # a column that refers to its own table (a repeat of an earlier run) is filled in after every row is there
            selfref = set(shared.execute(text("""SELECT a.attname FROM pg_constraint k JOIN pg_attribute a ON a.attrelid = k.conrelid
                                                   AND a.attnum = ANY(k.conkey)
                                                  WHERE k.contype = 'f' AND k.conrelid = to_regclass(:t) AND k.confrelid = k.conrelid"""),
                                         {"t": t}).scalars().all())
            for r in rows:
                vals = {c: (json.dumps(r[c]) if jsonish[c] and isinstance(r[c], (dict, list)) else r[c]) for c in cols}
                conn.execute(text(f"INSERT INTO {t} ({names}) {'OVERRIDING SYSTEM VALUE ' if ident else ''}VALUES ("  # noqa: S608
                                  + ", ".join(f":{c}" for c in cols) + ")"), {**vals, **{c: None for c in selfref}})
            for r in rows:
                for c in selfref:
                    if r[c] is not None:
                        conn.execute(text(f'UPDATE {t} SET "{c}" = :v WHERE '  # noqa: S608 - fixed names
                                          + " AND ".join(f'"{k}" = :k_{k}' for k in pk)), {"v": r[c], **{f"k_{k}": r[k] for k in pk}})
            for c in counted:                        # the id counter carries on after the highest copied id
                conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}', '{c}'), "
                                  f"GREATEST((SELECT max({c}) FROM {t}), 1))"))
            out[t] = len(rows)
            say(f"{t}: {len(rows)} row(s) copied")
    return out


def main(argv: list[str]) -> int:
    if argv[:1] == ["speed"]:                         # text comparisons measured (R2.52)
        from . import textspeed
        return textspeed.main()
    if argv[:1] == ["ensure"]:
        ensure()
        return 0
    if argv[:1] == ["copy"]:
        try:
            copy(argv[1] if len(argv) > 1 else "")
        except (ValueError, LookupError) as exc:
            print(exc)
            return 2
        print("Copied. The repository database's rows stay as they were (empty them with SQL when you are sure).")
        return 0
    rows = status(check="--no-check" not in argv)
    print("EA Explorer's databases (R2.50) and schemas (D630): empty setting = its schema in the repository database; set one to move it (docs/databases.md)")
    for r in rows:
        ok = "" if r["answers"] is None else ("  answers" if r["answers"] else f"  DOES NOT ANSWER: {r.get('error', '')}")
        print(f"  {r['key']:<15}{r['where']:<62}{r['setting']}{ok}")
    return 0 if all(r["answers"] is not False for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
