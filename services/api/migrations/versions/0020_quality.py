"""Phase 12 (version 0.13.0): validation and data quality (D239).

Revision ID: 0020_quality
Revises: 0019_backups
Create Date: 2026-11-06

The SQL lives in migrations/sql/0020_quality.sql (checked by tests/sql/phase12_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0020_quality"
down_revision = "0019_backups"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0020_quality.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0020 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS core.quality_told, core.quality_seals, core.quality_runs, core.quality_changes, "
                "core.quality_rules, core.quality_settings, core.quality_defaults; "
                "DELETE FROM core.schema_versions WHERE version = '0.13.0'")
