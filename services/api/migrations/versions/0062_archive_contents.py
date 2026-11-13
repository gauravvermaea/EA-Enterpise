"""What an archived model or project holds, as text, for Find (R2.41, D647); no version change.

Revision ID: 0062_archive_contents
Revises: 0061_farm_sites
Create Date: 2026-11-13

The SQL lives in migrations/sql/0062_archive_contents.sql.
"""

from pathlib import Path

from alembic import op

revision = "0062_archive_contents"
down_revision = "0061_farm_sites"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0062_archive_contents.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("ALTER TABLE archive.archive_store DROP COLUMN IF EXISTS contents")
