"""Phase 8.2 (version 0.8.2): viewpoints as data, report audiences, TOGAF catalogues and matrices, dependency reports.

Revision ID: 0012_viewpoints
Revises: 0011_grids
Create Date: 2026-11-05

The SQL lives in migrations/sql/0012_viewpoints.sql (checked by tests/sql/phase8_2_checks.sql). The built-in
viewpoints and audiences are loaded by the seed (eax.seed.catalog) from eax/report_defs.py on every start.
"""

from pathlib import Path

from alembic import op

revision = "0012_viewpoints"
down_revision = "0011_grids"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0012_viewpoints.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0012 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DROP VIEW IF EXISTS rpt.dr_fan, rpt.dr_impact_chain, rpt.dr_steps, rpt.dr_entity_choices, rpt.tm_capability_org,
            rpt.tm_data_security, rpt.tc_roles, rpt.tc_roadmap, rpt.tc_measures, rpt.tc_products, rpt.tc_locations,
            rpt.tc_requirements, rpt.tc_motivation_chain, rpt.tc_stakeholders, rpt.tc_principles, rpt.type_pairs,
            rpt.vp_element_values, rpt.vp_relationships, rpt.vp_elements, rpt.viewpoints CASCADE;
        DROP FUNCTION IF EXISTS rpt.f_dependencies(text, integer);
        DROP VIEW IF EXISTS rpt.dependency_edges;
        DROP TABLE IF EXISTS core.report_audience_links, core.report_audiences, core.viewpoints;
        DROP FUNCTION IF EXISTS core.viewpoints_guard();
        DELETE FROM core.schema_versions WHERE version = '0.8.2';
        """
    )
