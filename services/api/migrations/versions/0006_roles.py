"""Phase 3.1 (version 0.3.1): roles and permissions, model assignments, row-level security.

Revision ID: 0006_roles
Revises: 0005_metamodel_editing
Create Date: 2026-11-04

The SQL lives in migrations/sql/0006_roles.sql (checked by tests/sql/phase3_1_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0006_roles"
down_revision = "0005_metamodel_editing"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0006_roles.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DO $$
        DECLARE t text;
        BEGIN
            FOREACH t IN ARRAY ARRAY['models', 'entities', 'relationships', 'attribute_values'] LOOP
                EXECUTE format('DROP POLICY IF EXISTS read_by_model ON core.%I', t);
                EXECUTE format('DROP POLICY IF EXISTS add ON core.%I', t);
                EXECUTE format('DROP POLICY IF EXISTS change ON core.%I', t);
                EXECUTE format('DROP POLICY IF EXISTS remove ON core.%I', t);
                EXECUTE format('ALTER TABLE core.%I NO FORCE ROW LEVEL SECURITY', t);
                EXECUTE format('ALTER TABLE core.%I DISABLE ROW LEVEL SECURITY', t);
            END LOOP;
            FOREACH t IN ARRAY ARRAY['layers', 'entity_types', 'relationship_types', 'pick_lists', 'pick_list_values',
                                     'attribute_types', 'item_attributes', 'validation_rules', 'allowed_relationships',
                                     'metamodel_versions', 'models', 'model_users', 'entities', 'relationships',
                                     'attribute_values', 'display_id_counters'] LOOP
                EXECUTE format('DROP TRIGGER IF EXISTS %I ON core.%I', t || '_00_access', t);
            END LOOP;
        END $$;
        DROP TRIGGER IF EXISTS models_ancestors ON core.models;
        DROP TRIGGER IF EXISTS models_creator_role ON core.models;
        CREATE OR REPLACE FUNCTION core.can_read_model(p_model bigint) RETURNS boolean LANGUAGE sql STABLE AS $f$
            SELECT true
        $f$;
        DROP TABLE IF EXISTS core.role_mappings, core.app_roles, core.model_users, core.model_ancestors;
        DROP FUNCTION IF EXISTS core.refuse_unpermitted(), core.refuse_role_mapping_change(), core.refresh_model_ancestors(),
            core.why_not(bigint, text), core.assignments(), core.model_roles(bigint), core.first_role_by_creator(bigint),
            core.creator_becomes_model_admin(), core.check_global_role(), core.check_model_role(), core.may_read_model(bigint), core.is_library_model(bigint), core.readable_models(), core.sees_every_model(),
            core.session_roles();
        DELETE FROM core.schema_versions WHERE version = '0.3.1';
        """
    )
