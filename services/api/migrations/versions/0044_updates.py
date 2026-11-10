"""Version 0.19.0: updating to a new release from git (phase 36, D417); releases (8.5).

Revision ID: 0044_updates
Revises: 0043_deployment
Create Date: 2026-11-10

The SQL lives in migrations/sql/0044_updates.sql.
"""

from pathlib import Path

from alembic import op

revision = "0044_updates"
down_revision = "0043_deployment"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0044_updates.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0044 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS core.update_history")
