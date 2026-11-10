"""Version 0.17.0 (batch 1, D421): merging a child into its parent (phases 19 and 20) and dedupe within a model (phase 21).

Revision ID: 0034_merge_dedupe
Revises: 0033_drawn_views
Create Date: 2026-11-10

The SQL lives in migrations/sql/0034_merge_dedupe.sql (checked by tests/test_merge_back.py).
"""

from pathlib import Path

from alembic import op

revision = "0034_merge_dedupe"
down_revision = "0033_drawn_views"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0034_merge_dedupe.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0034 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DROP TABLE IF EXISTS core.entity_aliases;
                   DROP TABLE IF EXISTS core.merge_requests;
                   DELETE FROM core.model_tags WHERE kind = 'start';
                   ALTER TABLE core.model_tags DROP CONSTRAINT IF EXISTS model_tags_kind_check;
                   ALTER TABLE core.model_tags ADD CONSTRAINT model_tags_kind_check
                       CHECK (kind IN ('manual', 'before-restore', 'backup'));
                   DELETE FROM core.schema_versions WHERE migration = '0034_merge_dedupe'""")
