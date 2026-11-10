"""Version 0.18.0: published import formats and deliveries (phase 34 and 34.1); a model from a metamodel workbook (D419).

Revision ID: 0042_import_formats
Revises: 0041_scenarios
Create Date: 2026-11-10

The SQL lives in migrations/sql/0042_import_formats.sql (checked by tests/test_import_formats.py).
"""

from pathlib import Path

from alembic import op

revision = "0042_import_formats"
down_revision = "0041_scenarios"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0042_import_formats.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0042 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""ALTER TABLE core.loads DROP COLUMN IF EXISTS source_id, DROP COLUMN IF EXISTS delivery,
                       DROP COLUMN IF EXISTS accepted_by, DROP COLUMN IF EXISTS accepted_at,
                       DROP COLUMN IF EXISTS declined_by, DROP COLUMN IF EXISTS declined_at;
                   DROP TABLE IF EXISTS core.import_sources""")
