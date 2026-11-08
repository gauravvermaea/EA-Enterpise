"""Phase 13.0.7 (version 0.14.7): the content framework on each project (D299).

Revision ID: 0029_content_framework
Revises: 0028_repository_table
Create Date: 2026-11-08

The SQL lives in migrations/sql/0029_content_framework.sql (checked by tests/test_content_framework.py).
"""

from pathlib import Path

from alembic import op

revision = "0029_content_framework"
down_revision = "0028_repository_table"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0029_content_framework.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0029 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DROP TABLE IF EXISTS proj.org_people;
                   ALTER TABLE proj.stakeholders DROP COLUMN entity_guid, DROP COLUMN entity_model;
                   ALTER TABLE core.entity_types DROP COLUMN content_area;
                   ALTER TABLE proj.lib_items DROP COLUMN content_area;
                   ALTER TABLE proj.items DROP COLUMN content_area;
                   ALTER TABLE proj.documents DROP COLUMN content_area;
                   DELETE FROM core.schema_versions WHERE version = '0.14.7'""")
