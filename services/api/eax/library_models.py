"""Library models in the library_models schema (R2.42, D633; owner, 12 Nov 2026, 21:25 and 13 Nov 2026: every read-only
shared model's content in its own schema with its own connection string, read from there by every screen; the full
split; schemas only, no new database).

What moves: the content of each library model (kind reference: the industry and seed reference models and the models
published to the model library) in CONTENT, model by model, at start-up in the background, with progress. Its row stays
in core.models (the directory every list, picker, link and permission uses) and says core.models.content_schema =
'library_models'. Working models and root metamodels stay where they are.

How it is read: a request (or background task, or MCP tool) about a library model gets a connection of the library
engine (route()), on which every statement naming a content table (core.entities, history.row_versions ...) is
rewritten to name the library_models table instead. So every screen's queries work unchanged; nothing else in core is
touched. The library engine is the library_models setting's (EAX_LIBRARY_MODELS_DB_URL) or, empty, the repository's.

Making a model from a library model copies across (copy_from_library): the metamodel document and the content package
read on a library connection, loaded into the new model in core with its own ids, as a package upload does.
"""

from __future__ import annotations

import contextvars
import logging
import re
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

SCHEMA = "library_models"
# the content tables, parents before children (moving in copies in this order and removes in the reverse)
CONTENT = ("layers", "pick_lists", "pick_list_values", "attribute_types", "entity_types", "relationship_types",
           "item_attributes", "allowed_relationships", "item_attribute_mappings", "validation_rules", "metamodel_versions",
           "metamodel_version_changes", "display_id_counters", "model_icons", "entities", "entity_aliases", "entity_icons",
           "attribute_values", "relationships")
HISTORY = "row_versions"           # history.row_versions -> library_models.row_versions
_RE = re.compile(r"\bcore\.(" + "|".join(CONTENT) + r")\b")
_RE_HIST = re.compile(r"\bhistory\.row_versions\b")
_BY_ENTITY = {"entity_icons"}      # no model_id: the rows of the model's entities


_RE_CAN_READ = re.compile(r"\bcore\.can_read_model\(([^()]*)\)")


def rewrite(sql: str, apart: bool = False) -> str:
    """A statement as it runs on a library connection: the content tables named in library_models. In a database of its
    own (apart), the repository's permission function is not there: a library model is readable by everyone signed in."""
    out = _RE_HIST.sub(f"{SCHEMA}.{HISTORY}", _RE.sub(lambda m: f"{SCHEMA}.{m.group(1)}", sql))
    return _RE_CAN_READ.sub(r"(\1 IS NOT NULL OR true)", out) if apart else out


# ---------------------------------------------------------------- the library engine and routing
@lru_cache(maxsize=1)
def engine() -> Engine:
    """The library engine: its own pool on the library_models setting's database (the repository's when empty), where
    each statement is rewritten (rewrite()) and the person asking is told to the database as on the main engine."""
    from . import databases, permissions
    from .config import get_settings
    db = databases.BY_KEY["library_models"]
    url = databases.sqlalchemy_url(databases.setting(db)) if databases.setting(db) else get_settings().sqlalchemy_url
    eng = create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=4,
                        connect_args={"connect_timeout": 5, "application_name": "eaexplorer-library-models"})

    apart = bool(databases.setting(db)) and databases.own(db)

    @event.listens_for(eng, "before_cursor_execute", retval=True)
    def _to_library(conn, cursor, statement, parameters, context, executemany):
        return rewrite(statement, apart), parameters

    @event.listens_for(eng, "checkout")
    def _who(dbapi_connection, _record, _proxy):
        who = permissions.current.get()
        with dbapi_connection.cursor() as cur:
            cur.execute("SELECT set_config('eax.actor', %s, false), set_config('eax.user_roles', %s, false)",
                        (who.username if who else "", (",".join(who.roles) or "none") if who else ""))
        dbapi_connection.commit()

    @event.listens_for(eng, "checkin")
    def _clean(dbapi_connection, _record):
        try:
            dbapi_connection.rollback()
            with dbapi_connection.cursor() as cur:
                cur.execute("DISCARD TEMP")
                cur.execute("SELECT set_config('eax.actor', '', false), set_config('eax.user_roles', '', false)")
            dbapi_connection.commit()
        except Exception:  # noqa: BLE001 - the pool replaces a broken connection
            pass
    return eng


_routed: contextvars.ContextVar[bool] = contextvars.ContextVar("eax_library_routed", default=False)


def routed() -> bool:
    return _routed.get()


@contextmanager
def route(on: bool = True):
    """Inside it, get_engine() gives the library engine (a library model's request, task or tool)."""
    token = _routed.set(bool(on))
    try:
        yield
    finally:
        _routed.reset(token)


def set_route(on: bool):
    """For a request: from before_request to teardown (reset with the token it returns)."""
    return _routed.set(bool(on))


def reset_route(token) -> None:
    try:
        _routed.reset(token)
    except (ValueError, LookupError):
        _routed.set(False)


_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def is_library(ref: Any) -> bool:
    """Whether the model (its guid, or its id) has its content in the library schema. Asked of core.models on the
    repository's engine, so it answers whatever the route."""
    if ref is None or ref == "":
        return False
    from .db import base_engine
    try:
        with base_engine().connect() as c:
            if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
                v = c.execute(text("SELECT content_schema FROM core.models WHERE id = :i"), {"i": int(ref)}).scalar()
            elif _GUID.match(str(ref)):
                v = c.execute(text("SELECT content_schema FROM core.models WHERE guid = CAST(:g AS uuid)"), {"g": str(ref)}).scalar()
            else:
                v = c.execute(text("SELECT content_schema FROM core.models WHERE lower(name) = lower(:n) AND NOT is_deleted "
                                   "ORDER BY id LIMIT 1"), {"n": str(ref)}).scalar()
    except Exception:  # noqa: BLE001 - before the migration, or no database: not a library model
        return False
    return v == SCHEMA


MODEL_KEYS = ("model_id", "model", "model_guid", "source", "mid")


def model_of(view_args: dict | None, args: Any = None) -> Any:
    """The model a request or a tool call is about: its path's model, else ?model=."""
    for k in MODEL_KEYS:
        v = (view_args or {}).get(k)
        if v:
            return str(v)
    if args is not None:
        v = args.get("model") if hasattr(args, "get") else None
        if v:
            return str(v)
    return None


# ---------------------------------------------------------------- moving a model's content in (and back)
def _cols(conn, schema: str, table: str) -> list[str]:
    return [r[0] for r in conn.execute(text("""SELECT column_name FROM information_schema.columns
                                                WHERE table_schema = :s AND table_name = :t ORDER BY ordinal_position"""),
                                       {"s": schema, "t": table}).all()]


def _where(table: str, alias: str = "") -> str:
    a = f"{alias}." if alias else ""
    return (f"{a}entity_id IN (SELECT id FROM {{src}}.entities WHERE model_id = :m)" if table in _BY_ENTITY
            else f"{a}model_id = :m")


def _identity(conn, schema: str, table: str) -> bool:
    return bool(conn.execute(text("""SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
                                      JOIN pg_namespace n ON n.oid = c.relnamespace
                                     WHERE n.nspname = :s AND c.relname = :t AND a.attidentity IN ('a', 'd') LIMIT 1"""),
                                 {"s": schema, "t": table}).first())


def _copy(conn, model_id: int, src: str, dst: str, tables, hist_src: str, hist_dst: str) -> dict[str, int]:
    out = {}
    for t in tables:
        cols = [c for c in _cols(conn, dst, t) if c in set(_cols(conn, src, t))]
        names = ", ".join(f'"{c}"' for c in cols)
        over = "OVERRIDING SYSTEM VALUE " if _identity(conn, dst, t) else ""
        n = conn.execute(text(f"INSERT INTO {dst}.{t} ({names}) {over}SELECT {names} FROM {src}.{t} "   # noqa: S608 - fixed names
                              f"WHERE {_where(t).format(src=src)}"), {"m": model_id}).rowcount
        out[t] = n
    hs, hd = hist_src.split("."), hist_dst.split(".")
    cols = [c for c in _cols(conn, hd[0], hd[1]) if c in set(_cols(conn, hs[0], hs[1]))]
    names = ", ".join(f'"{c}"' for c in cols)
    over = "OVERRIDING SYSTEM VALUE " if _identity(conn, hd[0], hd[1]) else ""
    out["history"] = conn.execute(text(f"INSERT INTO {hist_dst} ({names}) {over}SELECT {names} FROM {hist_src} "  # noqa: S608
                                       "WHERE model_id = :m"), {"m": model_id}).rowcount
    return out


def _remove(conn, model_id: int, schema: str, tables, history: str) -> None:
    for t in reversed(tables):
        if schema == "core" and t in ("entities", "relationships", "attribute_values", "entity_aliases", "entity_icons"):
            # rows other models keep about these (quality findings) go first; there are none for a library model
            pass
        conn.execute(text(f"DELETE FROM {schema}.{t} WHERE {_where(t).format(src=schema)}"), {"m": model_id})  # noqa: S608
    if history == "history.row_versions":
        pass     # the repository's history is append-only: drop_core_history() removes it after, as its owner
    else:
        conn.execute(text(f"DELETE FROM {history} WHERE model_id = :m"), {"m": model_id})  # noqa: S608


def _powers(conn, by: str) -> None:
    """The move is the application's own work (D248): it may change a read-only library model's rows."""
    conn.execute(text("SELECT set_config('eax.actor', :a, true), set_config('eax.user_roles', 'super-admin', true), "
                      "set_config('eax.rls_bypass', 'on', true), set_config('eax.copy_into', '', true)"), {"a": by})


def _unlock(conn, model_id: int) -> bool:
    """Whether the model is locked (read-only): its rows then move only on the installer's connection (move_all), which
    the database lets change a locked model; a model not yet locked moves on any connection."""
    return bool(conn.execute(text("SELECT is_locked FROM core.models WHERE id = :i"), {"i": model_id}).scalar())


def move_in(conn, model_id: int, by: str = "system") -> dict:
    """One library model's content from core into library_models, in the caller's transaction (all or nothing): copied,
    then removed from core (its history last, the guard lifted inside this transaction only); then marked."""
    m = conn.execute(text("SELECT id, name, kind_code, content_schema FROM core.models WHERE id = :i"), {"i": model_id}).mappings().first()
    if not m:
        raise LookupError(f"No model {model_id}.")
    if m["content_schema"] == SCHEMA:
        return {"model": m["name"], "moved": False}
    if m["kind_code"] != "reference":
        raise ValueError(f"{m['name']} is not a library model: only library models move to the library schema.")
    _powers(conn, by)
    locked = _unlock(conn, model_id)
    counts = _copy(conn, model_id, "core", SCHEMA, CONTENT, "history.row_versions", f"{SCHEMA}.{HISTORY}")
    # who refers to these rows from core: nothing for a library model; the delete says so if something does
    _remove(conn, model_id, "core", CONTENT, "history.row_versions")
    conn.execute(text("UPDATE core.models SET content_schema = :s, is_locked = :l WHERE id = :i"),
                 {"s": SCHEMA, "i": model_id, "l": locked})
    return {"model": m["name"], "moved": True, "rows": counts}


def drop_core_history(conn) -> int:
    """The repository's history rows of models whose content (and history) moved into the library schema, removed with
    the append-only guard lifted inside this transaction only, as the table's owner (the application's login). Rows the
    move added while removing (its deletions) go too. Returns the rows removed."""
    ids = [r[0] for r in conn.execute(text("""SELECT DISTINCT h.model_id FROM history.row_versions h
                                               JOIN core.models m ON m.id = h.model_id AND m.content_schema = :s"""),
                                      {"s": SCHEMA}).all()]
    if not ids:
        return 0
    conn.execute(text("ALTER TABLE history.row_versions DISABLE TRIGGER row_versions_no_change"))
    n = conn.execute(text("DELETE FROM history.row_versions WHERE model_id = ANY(:i)"), {"i": ids}).rowcount
    conn.execute(text("ALTER TABLE history.row_versions ENABLE TRIGGER row_versions_no_change"))
    on = conn.execute(text("SELECT tgenabled FROM pg_trigger WHERE tgname = 'row_versions_no_change' "
                           "AND tgrelid = 'history.row_versions'::regclass")).scalar()
    if on != "O":
        raise RuntimeError("The history guard did not come back on: nothing is removed.")
    return int(n or 0)


def move_back(conn, model_id: int, by: str = "system") -> dict:
    """The reverse (a library model made a working model again, or the downgrade): from library_models into core."""
    m = conn.execute(text("SELECT id, name, content_schema FROM core.models WHERE id = :i"), {"i": model_id}).mappings().first()
    if not m or m["content_schema"] != SCHEMA:
        return {"model": m["name"] if m else model_id, "moved": False}
    _powers(conn, by)
    locked = _unlock(conn, model_id)
    counts = _copy(conn, model_id, SCHEMA, "core", CONTENT, f"{SCHEMA}.{HISTORY}", "history.row_versions")
    _remove(conn, model_id, SCHEMA, CONTENT, f"{SCHEMA}.{HISTORY}")
    conn.execute(text("UPDATE core.models SET content_schema = 'core', is_locked = :l WHERE id = :i"), {"i": model_id, "l": locked})
    return {"model": m["name"], "moved": True, "rows": counts}


def waiting(conn) -> list[dict]:
    """The library models whose content is still in core."""
    return [dict(r) for r in conn.execute(text("""SELECT id, name FROM core.models
                                                   WHERE kind_code = 'reference' AND content_schema = 'core' AND NOT is_deleted
                                                   ORDER BY id""")).mappings()]


def move_all(progress=lambda _p, _n: None, by: str = "system") -> list[str]:
    """Every library model still in core moved in, one transaction each (start-up, in the background, with progress)."""
    from .db import base_engine, installer_engine
    with base_engine().connect() as c:
        todo = waiting(c)
    out = []
    for i, m in enumerate(todo, start=1):
        progress(int(100 * (i - 1) / max(len(todo), 1)), f"Library models into their schema: {m['name']} ({i} of {len(todo)})")
        with installer_engine().begin() as c:       # a locked (published) library model: the installer's work
            r = move_in(c, m["id"], by)
        out.append(f"{m['name']}: {sum((r.get('rows') or {}).values())} rows")
    with base_engine().begin() as c:                 # and their history, now in the library schema, out of core
        gone = drop_core_history(c)
    if gone:
        out.append(f"{gone} history rows now kept in the library schema")
    from . import databases
    if todo and databases.own(databases.BY_KEY["library_models"]):
        # the library schema lives in a database of its own: the rows moved here go there, with the directory
        databases.copy("library_models", say=lambda _m: None)
        databases.sync_directory()
    return out


# ---------------------------------------------------------------- reading a library model from elsewhere
@contextmanager
def connect():
    """A library connection (reads only; the caller's own transaction is not shared)."""
    with engine().connect() as c:
        yield c


@contextmanager
def reading(conn, model: Any):
    """The connection to read one model's content on, whatever the route: a library connection for a library model, the
    repository's for any other; conn itself when it already reads the right place."""
    lib = is_library(model)
    if lib == routed():
        yield conn
        return
    if lib:
        with connect() as lc:
            yield lc
        return
    from .db import base_engine
    with base_engine().connect() as bc:
        yield bc


def copy_from_library(conn, src_guid: str, dst_id: int, content: bool, history: bool = False) -> dict:
    """A model made from a library model (R2.42): its metamodel, and with content its entities, values and relationships,
    read on a library connection and loaded into the new model (dst_id, in core, conn's transaction) with its own ids."""
    from . import model_ops as mo
    with connect() as lc:
        spec = mo.metamodel_spec(lc, src_guid)
        data = mo.package_content(lc, src_guid) if content else None
        hist = mo.history_portable(lc, int(lc.execute(text("SELECT id FROM core.models WHERE guid = CAST(:g AS uuid)"),
                                                     {"g": src_guid}).scalar())) if (content and history) else None
    counts = mo.apply_spec(conn, dst_id, spec, "new")
    out = {"metamodel": sum(v for v in counts.values() if isinstance(v, int))}
    if data:
        out.update(mo.load_content(conn, dst_id, data["entities"], data["relationships"], spec))
    if hist:
        out["history_rows"] = mo.load_history(conn, dst_id, hist, "Before the copy, in the library")
    return out


def search(q: str, limit: int = 50) -> list[dict]:
    """Find in the library models' entities (Find with library models): name or display id contains q."""
    if not (q or "").strip():
        return []
    with connect() as lc:
        return [dict(r) for r in lc.execute(text("""
            SELECT e.guid AS id, e.display_id, e.name, et.name AS entity_type, m.guid AS model_id, m.name AS model, true AS library
              FROM core.entities e JOIN core.entity_types et ON et.id = e.entity_type_id JOIN core.models m ON m.id = e.model_id
             WHERE NOT e.is_deleted AND (e.name ILIKE :q OR e.display_id ILIKE :q)
             ORDER BY m.name, e.name LIMIT :l"""), {"q": f"%{q.strip()}%", "l": int(limit)}).mappings()]


def main(argv: list[str]) -> int:
    """python -m eax.library_models move|back ID|status."""
    from .db import base_engine
    if argv[:1] == ["move"]:
        for line in move_all(lambda p, n: print(n)):
            print(line)
        return 0
    if argv[:1] == ["back"] and len(argv) > 1:
        from .db import installer_engine
        with installer_engine().begin() as c:
            print(move_back(c, int(argv[1])))
        return 0
    with base_engine().connect() as c:
        rows = c.execute(text("SELECT content_schema, count(*) FROM core.models WHERE kind_code = 'reference' AND NOT is_deleted "
                              "GROUP BY 1")).all()
    print("library models by where their content is:", dict(rows))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
