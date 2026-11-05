"""Phase 10.1 (version 0.10.1): import and export sheets, loads and column mappings (D197).

Revision ID: 0017_sheets
Revises: 0016_settings
Create Date: 2026-11-05

The SQL lives in migrations/sql/0017_sheets.sql (checked by tests/sql/phase10_1_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0017_sheets"
down_revision = "0016_settings"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0017_sheets.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0017 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DROP TABLE IF EXISTS core.loads, core.column_mappings, core.task_files;
        DELETE FROM core.schema_versions WHERE version = '0.10.1';
        """
    )
