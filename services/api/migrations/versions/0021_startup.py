"""Phase 12.1 (version 0.13.1): start-up in two tiers (D255).

Revision ID: 0021_startup
Revises: 0020_quality
Create Date: 2026-11-06

The SQL lives in migrations/sql/0021_startup.sql (checked by tests/test_startup.py).
"""

from pathlib import Path

from alembic import op

revision = "0021_startup"
down_revision = "0020_quality"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0021_startup.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0021 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS core.startup_parts; DELETE FROM core.schema_versions WHERE version = '0.13.1'")
