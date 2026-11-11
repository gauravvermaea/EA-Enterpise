"""Database checks of the self-test (phase 36.1, D367): the database is what the API and the rules expect. Each check
is a read-only query on the live database (it changes nothing); a check passes when its query finds nothing wrong."""

from __future__ import annotations

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
    ("foreign keys have an index (speed)", """
        SELECT c.conrelid::regclass || '(' || a.attname || ')' FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
         WHERE c.contype = 'f' AND array_length(c.conkey, 1) = 1 AND c.connamespace::regnamespace::text IN ('core', 'proj')
           AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1])
         LIMIT 100""", "warning"),
]


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
    for name, sql, bad in CHECKS:
        t0 = time.time()
        try:
            rows = [str(r[0]) for r in conn.execute(text(sql)).all()]
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            record(name, "failed", f"the check could not run: {exc}", 0)
            continue
        ms = int((time.time() - t0) * 1000)
        record(name, bad if rows else "passed", "; ".join(rows[:50]) + (f" (and {len(rows) - 50} more)" if len(rows) > 50 else "")
               if rows else "nothing wrong", ms)
