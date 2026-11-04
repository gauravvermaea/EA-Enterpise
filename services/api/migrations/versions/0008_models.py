"""Phase 4 (version 0.4.0): create, copy and share models; Library Admin; metamodel drafts.

Revision ID: 0008_models
Revises: 0007_relationship_rules
Create Date: 2026-11-04

The SQL lives in migrations/sql/0008_models.sql (checked by tests/sql/phase4_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0008_models"
down_revision = "0007_relationship_rules"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0008_models.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); the downgrade removes what 0008 added and puts back the
    # functions it replaced from their earlier migrations.
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DROP TABLE IF EXISTS core.metamodel_drafts;
        DROP FUNCTION IF EXISTS core.copy_model(bigint, bigint, boolean);
        DROP TRIGGER IF EXISTS models_2_dependants ON core.models;
        DROP FUNCTION IF EXISTS core.refuse_delete_with_dependants();
        DROP TRIGGER IF EXISTS models_1_library_state ON core.models;
        DROP FUNCTION IF EXISTS core.default_library_state();
        ALTER TABLE core.models DROP CONSTRAINT IF EXISTS models_library_state;
        ALTER TABLE core.models DROP COLUMN IF EXISTS library_state, DROP COLUMN IF EXISTS copy_state,
            DROP COLUMN IF EXISTS copy_note, DROP COLUMN IF EXISTS history_from_source;
        DELETE FROM core.role_mappings WHERE app_role = 'library-admin';
        DELETE FROM core.app_roles WHERE code = 'library-admin';
        UPDATE core.app_roles SET sort_order = 6 WHERE code = 'user';
        DELETE FROM core.schema_versions WHERE migration = '0008_models';
        """
    )
    # The functions 0008 replaced (refuse_locked_model, refuse_unpermitted, refuse_retired_type,
    # check_relationship, check_attribute_value) keep their 0008 bodies: they behave as before when no
    # copy is running and nobody holds the Library Admin role. copying_into and may_curate_library stay
    # for them.
