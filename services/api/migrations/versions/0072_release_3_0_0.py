"""Version 3.0.0: Release 3 (records the version only).

Revision ID: 0072_release_3_0_0
Revises: 0071_discovery
Create Date: 2026-11-14

The SQL lives in migrations/sql/0072_release_3_0_0.sql.
"""

from pathlib import Path

from alembic import op

revision = "0072_release_3_0_0"
down_revision = "0071_discovery"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0072_release_3_0_0.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("DELETE FROM core.schema_versions WHERE version = '3.0.0'")
