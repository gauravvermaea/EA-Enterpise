"""Version 0.19.0: relationship attributes limited to allowed relationships (D563 to D565).

Revision ID: 0047_relationship_attributes
Revises: 0046_industry_packs
Create Date: 2026-11-10

The SQL lives in migrations/sql/0047_relationship_attributes.sql (checked by tests/test_relationship_attributes.py).
"""

from pathlib import Path

from alembic import op

revision = "0047_relationship_attributes"
down_revision = "0046_industry_packs"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0047_relationship_attributes.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0046 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS core.item_attribute_mappings")
