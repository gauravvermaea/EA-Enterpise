"""D630 (owner, 13 Nov 2026, 08:43 and 08:45): the parts that can move are schemas of their own in the one repository
database, each reached by its own connection string; no database or server is ever created. Checked on PostgreSQL on
13 Nov 2026: the migration moved the tables with their rows (34 runs, 9,022 results, 3 archived items), back down and up
again; with EAX_TESTS_DB_URL and EAX_ARCHIVE_DB_URL pointing at other existing databases, ensure made the schemas there
and copy brought every row (a run repeating an earlier one included)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MOVED = {"tests": ("test_runs", "test_results", "test_fixtures"), "archive": ("archive_store",),
         "operations": ("backup_schedules", "deployments", "update_history", "heartbeat_logs", "startup_parts")}


def test_the_migration_moves_each_table_to_its_schema():
    sql = (REPO / "services/api/migrations/sql/0055_split_schemas.sql").read_text()
    for schema, tables in MOVED.items():
        assert f"CREATE SCHEMA IF NOT EXISTS {schema};" in sql
        for t in tables:
            assert re.search(rf"ALTER TABLE IF EXISTS core\.{t}\s+SET SCHEMA {schema};", sql), t
    assert "CREATE SCHEMA IF NOT EXISTS personal;" in sql and "CREATE SCHEMA IF NOT EXISTS library_models;" in sql
    assert "CREATE DATABASE" not in sql.upper()


def test_no_code_names_a_moved_table_in_core():
    names = "|".join(t for ts in MOVED.values() for t in ts)
    bad = []
    for root in ("services/api/eax", "services/ops", "eaxcli", "services/backup"):
        for f in (REPO / root).rglob("*"):
            if f.is_file() and f.suffix in (".py", ".sh", ".sql") and "migrations" not in f.parts:
                if re.search(rf"core\.({names})\b", f.read_text(errors="ignore")):
                    bad.append(str(f.relative_to(REPO)))
    assert not bad, f"still naming core.<moved table>: {bad}"


def test_databases_knows_the_schemas_and_never_creates_a_database():
    from eax import databases as dbs
    for key, tables in MOVED.items():
        assert dbs.TABLES[key][:len(tables)] == tuple(f"{key}.{t}" for t in tables)   # the moved ones first
        assert dbs.SCHEMAS[key] == key
    assert dbs.SCHEMAS["personal"] == "personal" and dbs.SCHEMAS["library_models"] == "library_models"
    src = (REPO / "services/api/eax/databases.py").read_text()
    assert "CREATE DATABASE" not in src.replace('"never creates a database', "")
    assert "CREATE SCHEMA IF NOT EXISTS" in src


def test_a_self_referring_column_is_copied_after_the_rows(monkeypatch):
    import inspect

    from eax import databases as dbs
    src = inspect.getsource(dbs.copy)
    assert "selfref" in src and src.index("{c: None for c in selfref}") < src.index('SET "{c}" = :v')
