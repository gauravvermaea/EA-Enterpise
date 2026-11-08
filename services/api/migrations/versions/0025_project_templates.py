"""Phase 13.0.3 (version 0.14.3): model roles and project templates (D281, D282).

Revision ID: 0025_project_templates
Revises: 0024_project_setup
Create Date: 2026-11-07

The SQL lives in migrations/sql/0025_project_templates.sql (checked by tests/test_project_templates.py).
"""

from pathlib import Path

from alembic import op

revision = "0025_project_templates"
down_revision = "0024_project_setup"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0025_project_templates.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0025 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DROP TABLE IF EXISTS proj.project_templates;
                   ALTER TABLE proj.project_models DROP COLUMN role, DROP COLUMN role_seq;
                   ALTER TABLE proj.projects DROP COLUMN template_code;
                   DELETE FROM core.schema_versions WHERE version = '0.14.3'""")
