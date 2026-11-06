"""Phase 13 (version 0.14.0): architecture projects and their repository (D258).

Revision ID: 0022_projects
Revises: 0021_startup
Create Date: 2026-11-06

The SQL lives in migrations/sql/0022_projects.sql (checked by tests/test_projects.py).
"""

from pathlib import Path

from alembic import op

revision = "0022_projects"
down_revision = "0021_startup"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0022_projects.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0022 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP SCHEMA IF EXISTS proj CASCADE; DELETE FROM core.schema_versions WHERE version = '0.14.0'")
