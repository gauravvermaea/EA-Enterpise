"""Sites (R2.1, D646): the farm schema and farm.sites; no version change.

Revision ID: 0061_farm_sites
Revises: 0060_test_data_flag
Create Date: 2026-11-13

The SQL lives in migrations/sql/0061_farm_sites.sql.
"""

from pathlib import Path

from alembic import op

revision = "0061_farm_sites"
down_revision = "0060_test_data_flag"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0061_farm_sites.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS farm.sites; DROP SCHEMA IF EXISTS farm")
