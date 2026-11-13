"""Each part that can move in a schema of its own (D630); no database is created; no version change.

Revision ID: 0055_split_schemas
Revises: 0054_derived_types
Create Date: 2026-11-13

The SQL lives in migrations/sql/0055_split_schemas.sql.
"""

from pathlib import Path

from alembic import op

revision = "0055_split_schemas"
down_revision = "0054_derived_types"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0055_split_schemas.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    for schema, tables in (("tests", ("test_runs", "test_results", "test_fixtures")),
                           ("operations", ("backup_schedules", "deployments", "update_history", "heartbeat_logs", "startup_parts")),
                           ("archive", ("archive_store",))):
        for t in tables:
            raw.execute(f"ALTER TABLE IF EXISTS {schema}.{t} SET SCHEMA core")
