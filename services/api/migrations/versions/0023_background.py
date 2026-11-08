"""Phase 13.0.2 (version 0.14.1): slow actions as background tasks (D273).

Revision ID: 0023_background
Revises: 0022_projects
Create Date: 2026-11-06

The SQL lives in migrations/sql/0023_background.sql (checked by tests/test_background.py).
"""

from pathlib import Path

from alembic import op

revision = "0023_background"
down_revision = "0022_projects"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0023_background.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0023 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""ALTER TABLE core.notifications DROP CONSTRAINT notifications_category_check;
                   DELETE FROM core.notifications WHERE category = 'task';
                   ALTER TABLE core.notifications ADD CONSTRAINT notifications_category_check
                       CHECK (category IN ('commit', 'metamodel', 'request', 'model', 'system'));
                   ALTER TABLE core.task_files DROP COLUMN role;
                   DROP INDEX IF EXISTS core.tasks_requested_by_idx;
                   ALTER TABLE core.tasks DROP COLUMN link, DROP COLUMN progress, DROP COLUMN progress_note;
                   DELETE FROM core.schema_versions WHERE version = '0.14.1'""")
