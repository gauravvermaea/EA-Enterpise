"""Version 0.2.1: model screen additions after phase 2 (no schema change).

Revision ID: 0004_screens
Revises: 0003_library
Create Date: 2026-11-04

The SQL lives in migrations/sql/0004_screens.sql. It records version 0.2.1 in core.schema_versions,
which must match the API's version.toml.
"""

from pathlib import Path

from alembic import op

revision = "0004_screens"
down_revision = "0003_library"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0004_screens.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("DELETE FROM core.schema_versions WHERE version = '0.2.1'")
