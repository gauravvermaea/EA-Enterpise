"""Phase 8.3 (version 0.8.4): model tags (snapshots), comparison profiles, gap analyses (D172).

Revision ID: 0014_tags
Revises: 0013_commits
Create Date: 2026-11-05

The SQL lives in migrations/sql/0014_tags.sql (checked by tests/sql/phase8_3_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0014_tags"
down_revision = "0013_commits"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0014_tags.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0014 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DROP VIEW IF EXISTS rpt.gap_matrix, rpt.gap_items, rpt.gap_analyses;
        DROP FUNCTION IF EXISTS rpt.f_gap_items(), rpt.f_gap_analyses();
        DROP TABLE IF EXISTS core.gap_runs, core.gap_items, core.gap_analyses, core.compare_profiles, core.model_tags;
        DROP FUNCTION IF EXISTS core.model_tags_guard();
        DELETE FROM core.schema_versions WHERE version = '0.8.4';
        """
    )
