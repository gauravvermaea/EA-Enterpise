"""An entity type derived from another (R2.9, D629); no version change.

Revision ID: 0054_derived_types
Revises: 0053_archive_store
Create Date: 2026-11-13

The SQL lives in migrations/sql/0054_derived_types.sql.
"""

from pathlib import Path

from alembic import op

revision = "0054_derived_types"
down_revision = "0053_archive_store"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0054_derived_types.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    for sql in ("ALTER TABLE core.allowed_relationships DROP COLUMN IF EXISTS inherited_from",
                "ALTER TABLE core.item_attributes DROP COLUMN IF EXISTS inherited_from",
                "ALTER TABLE core.entity_types DROP CONSTRAINT IF EXISTS entity_types_not_own_base",
                "ALTER TABLE core.entity_types DROP COLUMN IF EXISTS base_type_id"):
        raw.execute(sql)
