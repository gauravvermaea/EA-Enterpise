"""Version 2.0.0: Release 2 (records the version only).

Revision ID: 0067_release_2_0_0
Revises: 0066_release_1_1_0
Create Date: 2026-11-13

The SQL lives in migrations/sql/0067_release_2_0_0.sql.
"""

from pathlib import Path

from alembic import op

revision = "0067_release_2_0_0"
down_revision = "0066_release_1_1_0"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0067_release_2_0_0.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("DELETE FROM core.schema_versions WHERE version = '2.0.0'")
