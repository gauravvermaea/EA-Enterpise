"""Version 0.17.0 (batch 1, D421): KPI trends, the OData feed and the report designer (phase 24).

Revision ID: 0035_kpi_odata_reports
Revises: 0034_merge_dedupe
Create Date: 2026-11-10

The SQL lives in migrations/sql/0035_kpi_odata_reports.sql (checked by tests/test_kpi_reports.py).
"""

from pathlib import Path

from alembic import op

revision = "0035_kpi_odata_reports"
down_revision = "0034_merge_dedupe"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0035_kpi_odata_reports.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0035 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DROP VIEW IF EXISTS rpt.kpi_trends;
                   DROP VIEW IF EXISTS rpt.report_designs;
                   DROP TABLE IF EXISTS core.kpi_values;
                   DROP TABLE IF EXISTS core.kpi_snapshots;
                   DROP TABLE IF EXISTS core.kpi_definitions;
                   DROP TABLE IF EXISTS core.report_designs;
                   DELETE FROM core.schema_versions WHERE migration = '0035_kpi_odata_reports'""")
