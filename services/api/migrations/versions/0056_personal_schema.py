"""Each person's data in the personal schema (R2.53, D632); no database is created; no version change.

Revision ID: 0056_personal_schema
Revises: 0055_split_schemas
Create Date: 2026-11-13

The SQL lives in migrations/sql/0056_personal_schema.sql.
"""

from pathlib import Path

from alembic import op

revision = "0056_personal_schema"
down_revision = "0055_split_schemas"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0056_personal_schema.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS core.personal_outbox")
    raw.execute("DROP TABLE IF EXISTS personal.settings")
    raw.execute("ALTER TABLE IF EXISTS personal.user_skills SET SCHEMA proj")
    for t in ("notifications", "notification_recipients", "requests", "request_comments", "favourites", "saved_views"):
        raw.execute(f"ALTER TABLE IF EXISTS personal.{t} SET SCHEMA core")
