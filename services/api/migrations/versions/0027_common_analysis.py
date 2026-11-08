"""Phase 13.0.5 (version 0.14.5): common analysis (D286).

Revision ID: 0027_common_analysis
Revises: 0026_model_wizards
Create Date: 2026-11-07

The SQL lives in migrations/sql/0027_common_analysis.sql (checked by tests/test_commons.py).
"""

from pathlib import Path

from alembic import op

revision = "0027_common_analysis"
down_revision = "0026_model_wizards"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0027_common_analysis.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0027 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DROP TABLE core.common_runs, core.common_items, core.common_analyses;
                   DELETE FROM core.schema_versions WHERE version = '0.14.5'""")
