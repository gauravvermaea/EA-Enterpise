"""Version 0.19.0: deployment kinds and eax deploy (phase 36, D498, D500 to D506).

Revision ID: 0043_deployment
Revises: 0042_import_formats
Create Date: 2026-11-10

The SQL lives in migrations/sql/0043_deployment.sql (it only records the version).
"""

from pathlib import Path

from alembic import op

revision = "0043_deployment"
down_revision = "0042_import_formats"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0043_deployment.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes the version row 0043 wrote.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DELETE FROM core.schema_versions WHERE migration = '0043_deployment'")
