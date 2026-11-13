"""Test data is marked on models and projects (R2.11, D637); no version change.

Revision ID: 0060_test_data_flag
Revises: 0059_files_schema
Create Date: 2026-11-13

The SQL lives in migrations/sql/0060_test_data_flag.sql.
"""

from pathlib import Path

from alembic import op

revision = "0060_test_data_flag"
down_revision = "0059_files_schema"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0060_test_data_flag.sql").read_text(encoding="utf-8"))
    # what earlier runs left is test data too: the models and projects tests.test_fixtures lists (when the tests schema
    # is in this database; apart, the next self-test removes them anyway, D593)
    if raw.execute("SELECT to_regclass('tests.test_fixtures')").fetchone()[0]:
        raw.execute("""UPDATE core.models m SET is_test_data = true FROM tests.test_fixtures f
                        WHERE f.kind = 'model' AND f.purged_at IS NULL AND f.ident = m.guid::text""")
        raw.execute("""UPDATE proj.projects p SET is_test_data = true FROM tests.test_fixtures f
                        WHERE f.kind = 'project' AND f.purged_at IS NULL AND f.ident = p.guid::text""")


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("ALTER TABLE core.models DROP COLUMN IF EXISTS is_test_data; "
                "ALTER TABLE proj.projects DROP COLUMN IF EXISTS is_test_data")
