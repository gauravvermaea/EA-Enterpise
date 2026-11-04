"""Phase 7 (version 0.7.0): grids, search, saved views and favourites.

Revision ID: 0011_grids
Revises: 0010_data_entry
Create Date: 2026-11-04

The SQL lives in migrations/sql/0011_grids.sql (checked by tests/sql/phase7_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0011_grids"
down_revision = "0010_data_entry"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0011_grids.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0011 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DROP INDEX IF EXISTS core.attribute_values_text_trgm_idx, core.entities_name_trgm_idx;
        DROP TABLE IF EXISTS core.favourites, core.saved_views;
        DELETE FROM core.schema_versions WHERE version = '0.7.0';
        """
    )
