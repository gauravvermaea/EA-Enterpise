"""Database checks of the self-test (phase 36.1, D367): the database is what the API and the rules expect. Each check
is a read-only query on the live database (it changes nothing); a check passes when its query finds nothing wrong."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable

# (name, query finding what is wrong (each row one problem), outcome when it finds something)
CHECKS: list[tuple[str, str, str]] = [
    ("every table has a primary key", """
        SELECT n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'r' AND n.nspname IN ('core', 'proj', 'changelog')
           AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'p')""", "failed"),
    ("every foreign key is validated", """
        SELECT conrelid::regclass || ': ' || conname FROM pg_constraint
         WHERE contype = 'f' AND NOT convalidated AND connamespace::regnamespace::text IN ('core', 'proj')""", "failed"),
    ("relationships join live entities of their own model", """
        SELECT r.guid::text FROM core.relationships r
          JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities t ON t.id = r.target_entity_id
         WHERE NOT r.is_deleted AND (s.is_deleted OR t.is_deleted OR s.model_id <> r.model_id OR t.model_id <> r.model_id)
         LIMIT 50""", "failed"),
    ("entities are of an entity type of their own model", """
        SELECT e.guid::text FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
         WHERE t.model_id <> e.model_id LIMIT 50""", "failed"),
    ("a parent is in the same model", """
        SELECT e.guid::text FROM core.entities e JOIN core.entities p ON p.id = e.parent_entity_id
         WHERE p.model_id <> e.model_id LIMIT 50""", "failed"),
    ("display IDs are unique within a model", """
        SELECT model_id || ' ' || display_id FROM core.entities WHERE NOT is_deleted AND display_id IS NOT NULL
         GROUP BY model_id, display_id HAVING count(*) > 1 LIMIT 50""", "failed"),
    ("relationship attributes are limited to allowed relationships of their own type and model", """
        SELECT x.guid::text FROM core.item_attribute_mappings x
          JOIN core.item_attributes i ON i.id = x.item_attribute_id
          JOIN core.allowed_relationships a ON a.id = x.allowed_relationship_id
         WHERE NOT x.is_deleted AND (i.relationship_type_id IS DISTINCT FROM a.relationship_type_id
                                     OR i.model_id <> x.model_id OR a.model_id <> x.model_id)
         LIMIT 50""", "failed"),
    ("the reporting login only reads", """
        SELECT 'eax_report may ' || p FROM unnest(ARRAY['INSERT', 'UPDATE', 'DELETE']) p
         WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report')
           AND has_table_privilege('eax_report', 'core.entities', p)""", "failed"),
    ("self-test fixtures are named after their run", """
        SELECT f.kind || ' ' || f.name FROM core.test_fixtures f JOIN core.test_runs r ON r.id = f.run_id
         WHERE f.purged_at IS NULL AND position(substr(replace(r.run_guid::text, '-', ''), 1, 12) IN f.name) = 0
         LIMIT 50""", "failed"),
    # D577: history stays whole, values fit their attribute, relationship values belong to their mapping
    ("history is append-only (its guard is in place)", """
        SELECT 'history.row_versions has no working append-only guard' WHERE NOT EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = 'row_versions_no_change'
               AND tgrelid = 'history.row_versions'::regclass AND tgenabled <> 'D')""", "failed"),
    ("every entity's current version is in its history", """
        SELECT e.guid::text || ' (version ' || e.row_version || ')' FROM core.entities e
         WHERE NOT EXISTS (SELECT 1 FROM history.row_versions h
                            WHERE h.table_name = 'entities' AND h.row_id = e.id AND h.row_version = e.row_version)
         LIMIT 50""", "failed"),
    ("every relationship's current version is in its history", """
        SELECT r.guid::text || ' (version ' || r.row_version || ')' FROM core.relationships r
         WHERE NOT EXISTS (SELECT 1 FROM history.row_versions h
                            WHERE h.table_name = 'relationships' AND h.row_id = r.id AND h.row_version = r.row_version)
         LIMIT 50""", "failed"),
    ("attribute values are stored as their attribute's type", """
        SELECT v.guid::text || ': ' || t.code || ' is ' || t.data_type_code FROM core.attribute_values v
          JOIN core.attribute_types t ON t.id = v.attribute_type_id JOIN core.data_types d ON d.code = t.data_type_code
         WHERE NOT v.is_deleted AND num_nonnulls(v.value_text, v.value_number, v.value_date, v.value_bool, v.value_ref) = 1
           AND NOT CASE d.storage WHEN 'text' THEN v.value_text IS NOT NULL WHEN 'number' THEN v.value_number IS NOT NULL
                                  WHEN 'date' THEN v.value_date IS NOT NULL WHEN 'boolean' THEN v.value_bool IS NOT NULL
                                  ELSE v.value_ref IS NOT NULL END
         LIMIT 50""", "failed"),
    ("attribute values are of their own model", """
        SELECT v.guid::text FROM core.attribute_values v JOIN core.attribute_types t ON t.id = v.attribute_type_id
         WHERE NOT v.is_deleted AND t.model_id <> v.model_id LIMIT 50""", "failed"),
    ("whole numbers are whole", """
        SELECT v.guid::text || ': ' || v.value_number FROM core.attribute_values v
          JOIN core.attribute_types t ON t.id = v.attribute_type_id
         WHERE NOT v.is_deleted AND t.data_type_code = 'integer' AND v.value_number <> trunc(v.value_number) LIMIT 50""", "failed"),
    ("pick-list values are on their pick list", """
        SELECT v.guid::text || ': ' || t.code || ' = ' || left(v.value_text, 60) FROM core.attribute_values v
          JOIN core.attribute_types t ON t.id = v.attribute_type_id
         WHERE NOT v.is_deleted AND t.data_type_code = 'list' AND v.value_text IS NOT NULL AND v.value_text <> ''
           AND NOT EXISTS (SELECT 1 FROM core.pick_list_values p
                            WHERE p.pick_list_id = t.pick_list_id AND p.value = v.value_text AND NOT p.is_deleted)
         LIMIT 50""", "warning"),
    ("links point to entities of the same model", """
        SELECT v.guid::text FROM core.attribute_values v JOIN core.entities e ON e.id = v.value_ref
         WHERE NOT v.is_deleted AND e.model_id <> v.model_id LIMIT 50""", "failed"),
    ("relationship attribute values belong to their relationship type", """
        SELECT v.guid::text || ': ' || t.code FROM core.attribute_values v
          JOIN core.relationships r ON r.id = v.relationship_id JOIN core.attribute_types t ON t.id = v.attribute_type_id
         WHERE NOT v.is_deleted AND NOT r.is_deleted
           AND NOT EXISTS (SELECT 1 FROM core.item_attributes i WHERE i.attribute_type_id = v.attribute_type_id
                              AND i.relationship_type_id = r.relationship_type_id AND NOT i.is_deleted)
         LIMIT 50""", "failed"),
    ("relationship attribute values belong to their mapping", """
        SELECT v.guid::text || ': ' || t.code FROM core.attribute_values v
          JOIN core.relationships r ON r.id = v.relationship_id JOIN core.attribute_types t ON t.id = v.attribute_type_id
          JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities g ON g.id = r.target_entity_id
          JOIN core.item_attributes i ON i.attribute_type_id = v.attribute_type_id
                                      AND i.relationship_type_id = r.relationship_type_id AND NOT i.is_deleted
         WHERE NOT v.is_deleted AND NOT r.is_deleted
           AND EXISTS (SELECT 1 FROM core.item_attribute_mappings x WHERE x.item_attribute_id = i.id AND NOT x.is_deleted)
           AND NOT EXISTS (SELECT 1 FROM core.item_attribute_mappings x
                             JOIN core.allowed_relationships a ON a.id = x.allowed_relationship_id
                            WHERE x.item_attribute_id = i.id AND NOT x.is_deleted
                              AND a.source_type_id = s.entity_type_id AND a.target_type_id = g.entity_type_id)
         LIMIT 50""", "failed"),
    ("foreign keys have an index (speed)", """
        SELECT c.conrelid::regclass || '(' || a.attname || ')' FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
         WHERE c.contype = 'f' AND array_length(c.conkey, 1) = 1 AND c.connamespace::regnamespace::text IN ('core', 'proj')
           AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1])
         LIMIT 100""", "warning"),
]


# checks of the self-test's own tables: they run on the tests database (store.tests), the rest on the repository
IN_TESTS_DB = {"self-test fixtures are named after their run"}


def run(conn, api_version: str, record: Callable[[str, str, str, int], None]) -> None:
    """conn: a read-only SQLAlchemy connection. Records one result per check."""
    import time

    from sqlalchemy import text
    t0 = time.time()
    have = [r[0] for r in conn.execute(text("SELECT version FROM core.schema_versions")).all()]
    if api_version in have:
        record("the database is at the API's version", "passed", api_version, int((time.time() - t0) * 1000))
    else:
        record("the database is at the API's version", "failed",
               f"the API is {api_version}; the database has {', '.join(sorted(have)[-3:]) or 'none'}", 0)
    from . import store
    for name, sql, bad in CHECKS:
        t0 = time.time()
        try:
            if name in IN_TESTS_DB:                  # the self-test's own tables are in the tests database (R2.28)
                with store.tests(conn) as tc:
                    rows = [str(r[0]) for r in tc.execute(text(sql)).all()]
            else:
                rows = [str(r[0]) for r in conn.execute(text(sql)).all()]
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            record(name, "failed", f"the check could not run: {exc}", 0)
            continue
        ms = int((time.time() - t0) * 1000)
        record(name, bad if rows else "passed", "; ".join(rows[:50]) + (f" (and {len(rows) - 50} more)" if len(rows) > 50 else "")
               if rows else "nothing wrong", ms)
    run_outside(conn, record)


# ---------------------------------------------------------------- outside the main database (D577)
EA_ID = re.compile(r'\bea_id="([0-9a-fA-F-]{36})"')
MAX_VIEWS = 500


def persist_json(folder: str | None) -> tuple[str, str]:
    """persist/ (D558): every .json file there reads as JSON. The folder is mounted read-only into the runner."""
    if not folder or not os.path.isdir(folder):
        return "skipped", "persist/ is not mounted in the runner (EAX_SELFTEST_PERSIST)"
    bad, seen = [], 0
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        seen += 1
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                json.load(f)
        except (OSError, ValueError) as exc:
            bad.append(f"{name}: {str(exc)[:120]}")
    if bad:
        return "failed", "; ".join(bad)
    return "passed", f"{seen} file(s) read as JSON" if seen else "no settings saved yet"


def bindings(views: dict[str, list[str]], found: dict[str, tuple[str, bool]]) -> tuple[str, str]:
    """Drawn-view bindings (D354): views maps 'view (model guid)' to the entity ids its shapes are bound to; found maps
    an entity id to (its model guid, deleted). Bound to an entity that does not exist or is another model's: failed;
    to a deleted entity: a warning (the view shows it struck through until someone tidies it)."""
    missing, foreign, deleted = [], [], []
    for key, ids in views.items():
        model = key.rsplit("(", 1)[-1].rstrip(")")
        for e in ids:
            hit = found.get(e.lower())
            if hit is None:
                missing.append(f"{key}: {e}")
            elif hit[0] != model:
                foreign.append(f"{key}: {e}")
            elif hit[1]:
                deleted.append(f"{key}: {e}")
    if missing or foreign:
        return "failed", "; ".join([f"bound to no entity: {x}" for x in missing[:20]]
                                    + [f"bound to another model's entity: {x}" for x in foreign[:20]])
    if deleted:
        return "warning", f"{len(deleted)} shape(s) bound to a deleted entity: " + "; ".join(deleted[:20])
    n = sum(len(v) for v in views.values())
    return "passed", f"{len(views)} view(s), {n} bound shape(s), every one an entity of its own model"


def drawn_view_bindings(conn, views_dsn: str | None) -> tuple[str, str]:
    """Reads the latest version of each live drawn view from the views' database (read only), then the entities they name."""
    if not views_dsn:
        return "skipped", "the views service is off, or its database settings are not in the runner"
    import psycopg
    from sqlalchemy import text
    with psycopg.connect(views_dsn, connect_timeout=10) as vc:
        vc.read_only = True
        rows = vc.execute(f"""SELECT v.name, v.model_guid::text, x.xml FROM views.drawn_views v
                               JOIN LATERAL (SELECT xml FROM views.drawn_view_versions y WHERE y.view_id = v.id
                                              ORDER BY version_no DESC LIMIT 1) x ON true
                              WHERE NOT v.is_deleted ORDER BY v.modified_at DESC LIMIT {MAX_VIEWS}""").fetchall()
    views = {f"{name} ({model})": sorted({m.lower() for m in EA_ID.findall(xml or "")}) for name, model, xml in rows}
    ids = sorted({e for v in views.values() for e in v})
    found: dict[str, tuple[str, bool]] = {}
    for i in range(0, len(ids), 1000):
        for g, mg, dele in conn.execute(text("""SELECT e.guid::text, m.guid::text, e.is_deleted FROM core.entities e
                                                  JOIN core.models m ON m.id = e.model_id
                                                 WHERE e.guid = ANY(CAST(:ids AS uuid[]))"""), {"ids": ids[i:i + 1000]}).all():
            found[g.lower()] = (mg.lower(), dele)
    return bindings(views, found)


def views_dsn() -> str | None:
    """The views' database, from the same settings the views service reads (work/eaexplorer.env)."""
    e = os.environ.get
    if e("EAX_SERVICE_VIEWS", "on") == "off":
        return None
    laptop = e("EAX_DEPLOYMENT", "laptop") == "laptop"
    pw = e("EAX_VIEWS_DB_PASSWORD") or (e("EAX_DB_PASSWORD", "") if laptop else "")
    if not pw:
        return None
    from psycopg.conninfo import make_conninfo
    return make_conninfo(host=e("EAX_VIEWS_DB_HOST", e("EAX_DB_HOST", "db")), port=e("EAX_VIEWS_DB_PORT", e("EAX_DB_PORT", "5432")),
                         dbname=e("EAX_VIEWS_DB_NAME", "eaxviews"), user=e("EAX_VIEWS_DB_USER", "eax_views"), password=pw)


def run_outside(conn, record: Callable[..., None]) -> None:
    """The checks outside the main database: persist/ and the drawn views' bindings."""
    import time
    for name, fn in (("persist/ settings are valid JSON", lambda: persist_json(os.environ.get("EAX_SELFTEST_PERSIST", "/persist"))),
                     ("drawn views are bound only to their own model's entities", lambda: drawn_view_bindings(conn, views_dsn()))):
        t0 = time.time()
        try:
            outcome, detail = fn()
        except Exception as exc:  # noqa: BLE001
            outcome, detail = "warning", f"the check could not run: {str(exc).splitlines()[0][:200]}"
        record(name, outcome, detail, int((time.time() - t0) * 1000))
