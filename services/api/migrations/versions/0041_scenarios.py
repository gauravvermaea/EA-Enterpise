"""Version 0.18.0: scenario planning with AI (phase 27.1, D364, D490 to D495).

Revision ID: 0041_scenarios
Revises: 0040_mcp_activity
Create Date: 2026-11-10

The SQL lives in migrations/sql/0041_scenarios.sql (checked by tests/test_scenarios.py).
"""

from pathlib import Path

from alembic import op

revision = "0041_scenarios"
down_revision = "0040_mcp_activity"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0041_scenarios.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0041 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS proj.scenario_assessments")
