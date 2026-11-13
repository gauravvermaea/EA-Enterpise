"""The library models' content in the library_models schema (R2.42, D633); no database is created; no version change.

Revision ID: 0057_library_models
Revises: 0056_personal_schema
Create Date: 2026-11-13

The SQL lives in migrations/sql/0057_library_models.sql.
"""

from pathlib import Path

from alembic import op

revision = "0057_library_models"
down_revision = "0056_personal_schema"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0057_library_models.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    """Only while no library model has moved in (their content would be lost): the tables and the column go."""
    raw = op.get_bind().connection.driver_connection
    moved = raw.execute("SELECT count(*) FROM core.models WHERE content_schema = 'library_models'").fetchone()[0]
    if moved:
        raise RuntimeError(f"{moved} library model(s) have their content in library_models: move them back first "
                           "(python -m eax.library_models back)")
    raw.execute("DROP SCHEMA IF EXISTS library_models CASCADE")
    raw.execute("CREATE SCHEMA IF NOT EXISTS library_models")
    raw.execute("ALTER TABLE core.models DROP CONSTRAINT IF EXISTS models_content_schema_check")
    raw.execute("ALTER TABLE core.models DROP COLUMN IF EXISTS content_schema")
