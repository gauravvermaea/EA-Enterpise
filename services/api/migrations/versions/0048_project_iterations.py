"""Version 0.19.0: ADM iteration types on projects (D571 to D574).

Revision ID: 0048_project_iterations
Revises: 0047_relationship_attributes
Create Date: 2026-11-11

The SQL lives in migrations/sql/0048_project_iterations.sql (checked by tests/test_iterations.py).
"""

from pathlib import Path

from alembic import op

revision = "0048_project_iterations"
down_revision = "0047_relationship_attributes"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0048_project_iterations.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0048 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS proj.iteration_changes")
