"""A line on what each table is for, as its comment (D650); no version change.

Revision ID: 0064_about_tables
Revises: 0063_foreign_key_indexes
Create Date: 2026-11-13

The SQL lives in migrations/sql/0064_about_tables.sql. Downgrading leaves the comments (they change nothing).
"""

from pathlib import Path

from alembic import op

revision = "0064_about_tables"
down_revision = "0063_foreign_key_indexes"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0064_about_tables.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    pass
