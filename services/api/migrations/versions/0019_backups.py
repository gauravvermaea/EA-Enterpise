"""Phase 8.4 (version 0.12.0): backups and restores (D216).

Revision ID: 0019_backups
Revises: 0018_notifications
Create Date: 2026-11-06

The SQL lives in migrations/sql/0019_backups.sql (checked by tests/sql/phase8_4_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0019_backups"
down_revision = "0018_notifications"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0019_backups.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0019 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS core.backup_schedules; DELETE FROM core.schema_versions WHERE version = '0.12.0'")
