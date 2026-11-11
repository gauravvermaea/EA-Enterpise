"""Version 0.19.0: the self-test covers every page and real journeys (D575 to D578).

Revision ID: 0049_selftest_coverage
Revises: 0048_project_iterations
Create Date: 2026-11-11

The SQL lives in migrations/sql/0049_selftest_coverage.sql (checked by tests/test_selftest_coverage.py).
"""

from pathlib import Path

from alembic import op

revision = "0049_selftest_coverage"
down_revision = "0048_project_iterations"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0049_selftest_coverage.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0049 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("ALTER TABLE core.test_runs DROP COLUMN IF EXISTS journeys, DROP COLUMN IF EXISTS pages_only")
