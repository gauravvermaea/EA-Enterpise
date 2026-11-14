"""The API test harness's saved cases (R3.16): tests.api_cases; no version change.

Revision ID: 0069_api_cases
Revises: 0068_selftest_restore_suite
Create Date: 2026-11-13

The SQL lives in migrations/sql/0069_api_cases.sql.
"""

from pathlib import Path

from alembic import op

revision = "0069_api_cases"
down_revision = "0068_selftest_restore_suite"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0069_api_cases.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS tests.api_cases")
