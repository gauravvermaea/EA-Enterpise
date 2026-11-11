"""Version 1.0.0: Release 1 (records the version only).

Revision ID: 0050_release_1_0_0
Revises: 0049_selftest_coverage
Create Date: 2026-11-11

The SQL lives in migrations/sql/0050_release_1_0_0.sql.
"""

from pathlib import Path

from alembic import op

revision = "0050_release_1_0_0"
down_revision = "0049_selftest_coverage"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0050_release_1_0_0.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("DELETE FROM core.schema_versions WHERE version = '1.0.0'")
