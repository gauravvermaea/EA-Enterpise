"""Phase 10 (version 0.10.0): application and runtime settings for the administration console (D183).

Revision ID: 0016_settings
Revises: 0015_change_log
Create Date: 2026-11-05

The SQL lives in migrations/sql/0016_settings.sql (checked by tests/sql/phase10_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0016_settings"
down_revision = "0015_change_log"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0016_settings.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0016 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DROP TABLE IF EXISTS core.settings;
        DELETE FROM core.schema_versions WHERE version = '0.10.0';
        """
    )
