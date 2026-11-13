"""The file store for a platform with no local file system (R2.44, D635); no version change.

Revision ID: 0059_files_schema
Revises: 0058_remote_instances
Create Date: 2026-11-13

The SQL lives in migrations/sql/0059_files_schema.sql.
"""

from pathlib import Path

from alembic import op

revision = "0059_files_schema"
down_revision = "0058_remote_instances"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0059_files_schema.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS files.store")
