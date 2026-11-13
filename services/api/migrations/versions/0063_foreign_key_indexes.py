"""Every foreign key has an index (R2.24 part 4, D648); no version change.

Revision ID: 0063_foreign_key_indexes
Revises: 0062_archive_contents
Create Date: 2026-11-13

The SQL lives in migrations/sql/0063_foreign_key_indexes.sql. Downgrading removes the indexes it made (named *_fk).
"""

from pathlib import Path

from alembic import op

revision = "0063_foreign_key_indexes"
down_revision = "0062_archive_contents"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0063_foreign_key_indexes.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DO $$ DECLARE r record; BEGIN
                     FOR r IN SELECT schemaname, indexname FROM pg_indexes WHERE indexname LIKE '%\\_fk' ESCAPE '\\'
                                 AND schemaname NOT IN ('pg_catalog', 'information_schema') LOOP
                       EXECUTE format('DROP INDEX IF EXISTS %I.%I', r.schemaname, r.indexname);
                     END LOOP; END $$""")
