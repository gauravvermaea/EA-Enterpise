"""Run the failed ones again (R2.36, D605): a run repeats an earlier one's failed checks (no version change).

Revision ID: 0051_selftest_repeat
Revises: 0050_release_1_0_0
Create Date: 2026-11-12

The SQL lives in migrations/sql/0051_selftest_repeat.sql.
"""

from pathlib import Path

from alembic import op

revision = "0051_selftest_repeat"
down_revision = "0050_release_1_0_0"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0051_selftest_repeat.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("ALTER TABLE core.test_runs DROP COLUMN IF EXISTS repeat_of, DROP COLUMN IF EXISTS repeat_warnings, "
                "DROP COLUMN IF EXISTS followed_up_by, DROP COLUMN IF EXISTS fixture_ids")
