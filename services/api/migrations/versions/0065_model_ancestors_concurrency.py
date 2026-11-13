"""Two models made at once no longer collide in core.model_ancestors (D651); no version change.

Revision ID: 0065_model_ancestors_concurrency
Revises: 0064_about_tables
Create Date: 2026-11-13

The SQL lives in migrations/sql/0065_model_ancestors_concurrency.sql. Downgrading keeps the safer function.
"""

from pathlib import Path

from alembic import op

revision = "0065_model_ancestors_concurrency"
down_revision = "0064_about_tables"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0065_model_ancestors_concurrency.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    pass
