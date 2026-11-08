"""Version 0.15.1: repository tags and templates added to a document class (D312).

Revision ID: 0032_repository_tags
Revises: 0031_project_bases
Create Date: 2026-11-08

The SQL lives in migrations/sql/0032_repository_tags.sql (checked by tests/test_repo_tags.py).
"""

from pathlib import Path

from alembic import op

revision = "0032_repository_tags"
down_revision = "0031_project_bases"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0032_repository_tags.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0032 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DROP TABLE IF EXISTS proj.repo_tag_docs;
                   DROP TABLE IF EXISTS proj.repo_tags;
                   ALTER TABLE proj.items DROP COLUMN offered_templates;
                   ALTER TABLE proj.documents DROP COLUMN template_id;
                   DELETE FROM core.schema_versions WHERE version = '0.15.1'""")
