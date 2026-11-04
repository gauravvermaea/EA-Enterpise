"""Phase 2: schema versions, model properties and locked reference models.

Revision ID: 0003_library
Revises: 0002_metamodel
Create Date: 2026-11-04

The SQL lives in migrations/sql/0003_library.sql (tested directly against PostgreSQL). It moves the
database to version 0.2.0 (core.schema_versions), which must match the API's version.toml.
"""

from pathlib import Path

from alembic import op

revision = "0003_library"
down_revision = "0002_metamodel"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0003_library.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DO $$
        DECLARE t text;
        BEGIN
            FOREACH t IN ARRAY ARRAY['models', 'layers', 'entity_types', 'relationship_types', 'pick_lists',
                                     'pick_list_values', 'attribute_types', 'item_attributes', 'validation_rules',
                                     'allowed_relationships', 'entities', 'relationships', 'attribute_values',
                                     'display_id_counters'] LOOP
                EXECUTE format('DROP TRIGGER IF EXISTS %I ON core.%I', t || '_0_lock', t);
                EXECUTE format('DROP TRIGGER IF EXISTS %I ON core.%I', t || '_0_no_truncate', t);
            END LOOP;
        END $$;
        DROP FUNCTION IF EXISTS core.refuse_locked_model(), core.refuse_locked_content(), core.refuse_truncate(),
            core.is_installer(), core.schema_version();
        DROP INDEX IF EXISTS core.models_name_uq;
        CREATE UNIQUE INDEX models_name_uq ON core.models (lower(name)) WHERE NOT is_deleted;
        ALTER TABLE core.models DROP COLUMN IF EXISTS owner, DROP COLUMN IF EXISTS lifecycle,
            DROP COLUMN IF EXISTS industry, DROP COLUMN IF EXISTS version_label;
        DROP TABLE IF EXISTS core.schema_versions;
        """
    )
