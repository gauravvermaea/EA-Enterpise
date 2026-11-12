"""The self-test's fifth suite, backup (R2.45, D608): the suites' constraints take it (no version change).

Revision ID: 0052_selftest_backup_suite
Revises: 0051_selftest_repeat
Create Date: 2026-11-12

The SQL lives in migrations/sql/0052_selftest_backup_suite.sql.
"""

from pathlib import Path

from alembic import op

revision = "0052_selftest_backup_suite"
down_revision = "0051_selftest_repeat"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0052_selftest_backup_suite.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("DELETE FROM core.test_results WHERE suite = 'backup'")
    raw.execute("UPDATE core.test_runs SET suites = array_remove(suites, 'backup') WHERE 'backup' = ANY(suites)")
    raw.execute("ALTER TABLE core.test_results DROP CONSTRAINT IF EXISTS test_results_suite_check")
    raw.execute("ALTER TABLE core.test_results ADD CONSTRAINT test_results_suite_check "
                "CHECK (suite IN ('smoke', 'api', 'ui', 'db', 'security'))")
    raw.execute("ALTER TABLE core.test_runs DROP CONSTRAINT IF EXISTS test_runs_suites_check")
    raw.execute("ALTER TABLE core.test_runs ADD CONSTRAINT test_runs_suites_check "
                "CHECK (suites <@ ARRAY['api', 'ui', 'db', 'security']::text[] AND cardinality(suites) > 0)")
