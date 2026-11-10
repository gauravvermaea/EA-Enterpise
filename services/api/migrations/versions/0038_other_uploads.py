"""Version 0.17.0: a project's own uploads on the Other views and documents tab (D461).

Revision ID: 0038_other_uploads
Revises: 0037_surveys_maturity
Create Date: 2026-11-10

The SQL lives in migrations/sql/0038_other_uploads.sql (checked by tests/test_other_uploads.py).
"""

from pathlib import Path

from alembic import op

revision = "0038_other_uploads"
down_revision = "0037_surveys_maturity"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0038_other_uploads.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0038 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP INDEX IF EXISTS proj.documents_other; ALTER TABLE proj.documents DROP COLUMN IF EXISTS file_size")
