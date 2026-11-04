"""Phase 3 (version 0.3.0): metamodel editing, metamodel versions and history, model locks.

Revision ID: 0005_metamodel_editing
Revises: 0004_screens
Create Date: 2026-11-04

The SQL lives in migrations/sql/0005_metamodel_editing.sql (checked by tests/sql/phase3_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0005_metamodel_editing"
down_revision = "0004_screens"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0005_metamodel_editing.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DO $$
        DECLARE t text;
        BEGIN
            FOREACH t IN ARRAY ARRAY['layers', 'entity_types', 'relationship_types', 'pick_lists', 'pick_list_values',
                                     'attribute_types', 'item_attributes', 'validation_rules', 'allowed_relationships',
                                     'entities', 'relationships', 'attribute_values', 'display_id_counters'] LOOP
                EXECUTE format('DROP TRIGGER IF EXISTS %I ON core.%I', t || '_1_model_lock', t);
            END LOOP;
        END $$;
        DROP TRIGGER IF EXISTS entities_2_retired ON core.entities;
        DROP TRIGGER IF EXISTS attribute_values_2_retired ON core.attribute_values;
        DROP TRIGGER IF EXISTS relationships_2_retired ON core.relationships;
        DROP FUNCTION IF EXISTS core.refuse_retired_type();
        DROP TRIGGER IF EXISTS models_1_lock_level ON core.models;
        DROP TRIGGER IF EXISTS models_first_metamodel_version ON core.models;
        DROP FUNCTION IF EXISTS core.first_metamodel_version();
        DROP TRIGGER IF EXISTS entities_mm_version ON core.entities;
        DROP FUNCTION IF EXISTS core.refuse_model_lock(), core.check_model_lock(), core.stamp_mm_version(),
            core.refuse_version_under_lock() CASCADE;
        DROP FUNCTION IF EXISTS core.publish_metamodel_version(bigint, text), core.metamodel_version_at(bigint, timestamptz);
        DROP TABLE IF EXISTS core.metamodel_versions;
        ALTER TABLE core.entities DROP COLUMN IF EXISTS created_mm_version, DROP COLUMN IF EXISTS modified_mm_version;
        ALTER TABLE core.item_attributes DROP COLUMN IF EXISTS default_value, DROP COLUMN IF EXISTS help_text;
        ALTER TABLE core.models DROP COLUMN IF EXISTS lock_level, DROP COLUMN IF EXISTS lock_reason,
            DROP COLUMN IF EXISTS locked_at, DROP COLUMN IF EXISTS locked_by;
        DELETE FROM core.schema_versions WHERE version = '0.3.0';
        """
    )
