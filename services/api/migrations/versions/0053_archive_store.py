"""Archived and deleted models and projects in the archive store (R2.41, D626); no version change.

Revision ID: 0053_archive_store
Revises: 0052_selftest_backup_suite
Create Date: 2026-11-13

The SQL lives in migrations/sql/0053_archive_store.sql.
"""

from pathlib import Path

from alembic import op

revision = "0053_archive_store"
down_revision = "0052_selftest_backup_suite"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0053_archive_store.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS core.archive_store")
