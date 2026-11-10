"""Version 0.16.0: drawn views in draw.io, entity type notation, entity icons, junctions (phases 28 and 29).

Revision ID: 0033_drawn_views
Revises: 0032_repository_tags
Create Date: 2026-11-10

The SQL lives in migrations/sql/0033_drawn_views.sql (checked by tests/test_drawn_views.py).
"""

from pathlib import Path

from alembic import op

revision = "0033_drawn_views"
down_revision = "0032_repository_tags"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0033_drawn_views.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0033 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DROP TABLE IF EXISTS proj.view_evidence;
                   DROP TABLE IF EXISTS core.entity_icons;
                   ALTER TABLE core.entity_types DROP COLUMN notation, DROP COLUMN fill_colour, DROP COLUMN is_connector;
                   DELETE FROM core.schema_versions WHERE version = '0.16.0'""")
