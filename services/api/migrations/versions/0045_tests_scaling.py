"""Version 0.19.0: the self-test (phase 36.1) and scaling out (phase 36.3).

Revision ID: 0045_tests_scaling
Revises: 0044_updates
Create Date: 2026-11-10

The SQL lives in migrations/sql/0045_tests_scaling.sql (checked by tests/test_testing.py).
"""

from pathlib import Path

from alembic import op

revision = "0045_tests_scaling"
down_revision = "0044_updates"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0045_tests_scaling.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0045 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS core.test_fixtures; DROP TABLE IF EXISTS core.test_results; DROP TABLE IF EXISTS core.test_runs")
