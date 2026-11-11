"""Version 0.19.0: the industry packs' files in Documents (phase 39, D546 to D551).

Revision ID: 0046_industry_packs
Revises: 0045_tests_scaling
Create Date: 2026-11-10

The SQL lives in migrations/sql/0046_industry_packs.sql (checked by tests/test_industry_packs.py).
"""

from pathlib import Path

from alembic import op

revision = "0046_industry_packs"
down_revision = "0045_tests_scaling"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0046_industry_packs.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0046 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS core.industry_pack_files")
