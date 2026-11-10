"""Version 0.17.0: machine access (phase 25) and operations insight and housekeeping (phases 35 and 35.1).

Revision ID: 0036_machine_access_ops
Revises: 0035_kpi_odata_reports
Create Date: 2026-11-10

The SQL lives in migrations/sql/0036_machine_access_ops.sql (checked by tests/test_machine_access.py).
"""

from pathlib import Path

from alembic import op

revision = "0036_machine_access_ops"
down_revision = "0035_kpi_odata_reports"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0036_machine_access_ops.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0036 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DROP TABLE IF EXISTS core.archived_items;
                   DROP TABLE IF EXISTS core.housekeeping_runs;
                   DROP TABLE IF EXISTS core.retention_rules;
                   DROP TABLE IF EXISTS core.usage_daily;
                   DROP TABLE IF EXISTS core.machine_credentials;
                   DROP TABLE IF EXISTS core.service_accounts;
                   DELETE FROM core.schema_versions WHERE migration = '0036_machine_access_ops'""")
