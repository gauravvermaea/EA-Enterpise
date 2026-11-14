"""The self-test's sixth suite, restore (R3.8): its constraints only; no version change.

Revision ID: 0068_selftest_restore_suite
Revises: 0067_release_2_0_0
Create Date: 2026-11-13

The SQL lives in migrations/sql/0068_selftest_restore_suite.sql.
"""

from pathlib import Path

from alembic import op

revision = "0068_selftest_restore_suite"
down_revision = "0067_release_2_0_0"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0068_selftest_restore_suite.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    pass
