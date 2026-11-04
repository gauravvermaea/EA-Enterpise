"""Phase 5 (version 0.5.0): report views (rpt), standard reports SR-01 to SR-30, model access for reports.

Revision ID: 0009_reports
Revises: 0008_models
Create Date: 2026-11-04

The SQL lives in migrations/sql/0009_reports.sql (checked by tests/sql/phase5_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0009_reports"
down_revision = "0008_models"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0009_reports.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0009 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DO $$ DECLARE v record; BEGIN
            FOR v IN SELECT view_name FROM rpt.typed_views LOOP EXECUTE format('DROP VIEW IF EXISTS rpt.%I', v.view_name); END LOOP;
        END $$;
        DROP VIEW IF EXISTS rpt.sr30_source_comparison, rpt.sr29_change_activity, rpt.sr28_duplicates, rpt.sr27_orphans,
            rpt.sr26_completeness, rpt.sr25_rationalisation, rpt.sr24_single_points, rpt.sr23_obsolescence, rpt.sr22_impact,
            rpt.sr21_vendors, rpt.sr20_cost_by_capability, rpt.sr18_application_fit, rpt.sr17_technology_lifecycle, rpt.heat_thresholds;
        DROP FUNCTION IF EXISTS rpt.f_duplicates();
        DROP VIEW IF EXISTS rpt.mo_pick_list_counts, rpt.mo_recent_changes, rpt.mo_type_counts, rpt.sr_matrix, rpt.sr08_motivation,
            rpt.sr07_actors, rpt.sr06_interfaces, rpt.sr05_process_catalogue, rpt.sr04_data_catalogue, rpt.sr03_technology_inventory,
            rpt.sr02_capability_catalogue, rpt.sr01_application_inventory, rpt.entity_std, rpt.std_roles, rpt.entity_pairs,
            rpt.catalogue, rpt.model_access, rpt.changes, rpt.relationships, rpt.entity_values, rpt.entities, rpt.models;
        DROP FUNCTION IF EXISTS rpt.refresh_typed_views(), rpt.f_catalogue(), rpt.snake(text), rpt.f_model_access(), rpt.f_changes(),
            rpt.f_relationships(), rpt.f_entity_values(), rpt.f_entities(), rpt.f_models();
        DROP TABLE IF EXISTS rpt.typed_views, core.known_users;
        DELETE FROM core.schema_versions WHERE version = '0.5.0';
        """
    )
