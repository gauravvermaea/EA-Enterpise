"""Phase 9 (version 0.9.0): the change log, one row per action, in a database of its own (D180).

Revision ID: 0015_change_log
Revises: 0014_tags
Create Date: 2026-11-05

The SQL lives in migrations/sql/0015_change_log.sql (checked by tests/sql/phase9_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0015_change_log"
down_revision = "0014_tags"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0015_change_log.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0015 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DROP INDEX IF EXISTS history.row_versions_tx_idx;
        ALTER TABLE history.row_versions DROP COLUMN IF EXISTS tx;
        DROP INDEX IF EXISTS audit.events_tx_idx;
        ALTER TABLE audit.events DROP COLUMN IF EXISTS tx;
        DELETE FROM core.schema_versions WHERE version = '0.9.0';
        """
    )
