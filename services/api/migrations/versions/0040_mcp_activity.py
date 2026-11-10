"""Version 0.18.0: the MCP activity log and previews (phases 26 and 27, D368, D458, D482 to D489).

Revision ID: 0040_mcp_activity
Revises: 0038_other_uploads
Create Date: 2026-11-10

The SQL lives in migrations/sql/0040_mcp_activity.sql (checked by tests/test_mcp_ops.py).
"""

from pathlib import Path

from alembic import op

revision = "0040_mcp_activity"
down_revision = "0038_other_uploads"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0040_mcp_activity.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0040 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("DROP TABLE IF EXISTS core.mcp_previews; DROP TABLE IF EXISTS core.mcp_activity")
