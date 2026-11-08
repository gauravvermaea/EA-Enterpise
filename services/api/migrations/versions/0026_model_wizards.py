"""Phase 13.0.4 (version 0.14.4): model wizards (D283).

Revision ID: 0026_model_wizards
Revises: 0025_project_templates
Create Date: 2026-11-07

The SQL lives in migrations/sql/0026_model_wizards.sql (checked by tests/test_model_wizards.py).
"""

from pathlib import Path

from alembic import op

revision = "0026_model_wizards"
down_revision = "0025_project_templates"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0026_model_wizards.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0026 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""ALTER TABLE core.models DROP COLUMN frozen_at, DROP COLUMN frozen_by, DROP COLUMN frozen_note;
                   DELETE FROM core.schema_versions WHERE version = '0.14.4'""")
