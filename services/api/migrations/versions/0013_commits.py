"""Phase 8 (version 0.8.3): commits of content, Committer and History Viewer roles, draft rejection, model merges.

Revision ID: 0013_commits
Revises: 0012_viewpoints
Create Date: 2026-11-05

The SQL lives in migrations/sql/0013_commits.sql (checked by tests/sql/phase8_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0013_commits"
down_revision = "0012_viewpoints"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0013_commits.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes the tables 0013 added (the roles and functions stay).
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        ALTER TABLE core.pending_changes DROP CONSTRAINT IF EXISTS pending_changes_commit_fk;
        DROP TABLE IF EXISTS core.merge_sessions, core.commit_items, core.commits, core.pending_changes, core.change_sets;
        DELETE FROM core.schema_versions WHERE version = '0.8.3';
        """
    )
