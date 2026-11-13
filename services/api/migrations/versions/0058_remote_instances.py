"""Each person's remote instances and the recorded SSH sessions (R2.2, D634); no version change.

Revision ID: 0058_remote_instances
Revises: 0057_library_models
Create Date: 2026-11-13

The SQL lives in migrations/sql/0058_remote_instances.sql.
"""

from pathlib import Path

from alembic import op

revision = "0058_remote_instances"
down_revision = "0057_library_models"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0058_remote_instances.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS operations.ssh_sessions")
    raw.execute("DROP TABLE IF EXISTS personal.remote_instances")
