"""Faster text comparisons (R3.7, D665): a hash key index for exact name and value matches, trigram indexes for
"contains" on every column a search looks in; indexes only, no version change.

Revision ID: 0070_text_keys
Revises: 0069_api_cases
Create Date: 2026-11-13

The SQL lives in migrations/sql/0070_text_keys.sql.
"""

from pathlib import Path

from alembic import op

revision = "0070_text_keys"
down_revision = "0069_api_cases"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
INDEXES = ("core.entities_name_key_idx", "core.attribute_values_value_key_idx", "core.entities_display_id_lower_idx",
           "core.entities_display_id_trgm_idx", "core.entities_description_trgm_idx", "core.entity_aliases_old_name_trgm_idx",
           "core.entity_aliases_old_display_id_trgm_idx")


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0070_text_keys.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    for name in INDEXES:
        raw.execute(f"DROP INDEX IF EXISTS {name}")
