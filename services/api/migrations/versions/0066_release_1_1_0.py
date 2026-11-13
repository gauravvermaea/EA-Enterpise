"""Prepared as version 1.1.0 for Release 2; 2.0.0 was chosen (0067). Records nothing new.

Revision ID: 0066_release_1_1_0
Revises: 0065_model_ancestors_concurrency
Create Date: 2026-11-13

The SQL lives in migrations/sql/0066_release_1_1_0.sql.
"""

from pathlib import Path

from alembic import op

revision = "0066_release_1_1_0"
down_revision = "0065_model_ancestors_concurrency"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0066_release_1_1_0.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    pass
