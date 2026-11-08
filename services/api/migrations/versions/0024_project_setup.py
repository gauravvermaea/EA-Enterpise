"""Phase 13.0.1 (version 0.14.2): setting up and running an architecture project (D274-D279).

Revision ID: 0024_project_setup
Revises: 0023_background
Create Date: 2026-11-07

The SQL lives in migrations/sql/0024_project_setup.sql (checked by tests/test_project_setup.py).
"""

from pathlib import Path

from alembic import op

revision = "0024_project_setup"
down_revision = "0023_background"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0024_project_setup.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes the tables 0024 added (a clean rebuild removes the rest).
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DROP TABLE IF EXISTS proj.signoff_decisions, proj.signoff_requests;
                   ALTER TABLE proj.documents DROP COLUMN kind, DROP COLUMN signed_version;
                   ALTER TABLE proj.project_viewpoints DROP COLUMN own;
                   ALTER TABLE proj.items DROP COLUMN placeholder, DROP COLUMN templates, DROP COLUMN note;
                   DELETE FROM core.schema_versions WHERE version = '0.14.2'""")
