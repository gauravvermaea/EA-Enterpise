"""0.3.1: rules that an entity has a relationship of a type, to or from a type (D113).

Revision ID: 0007_relationship_rules
Revises: 0006_roles
Create Date: 2026-11-04

The SQL lives in migrations/sql/0007_relationship_rules.sql.
"""

from pathlib import Path

from alembic import op

revision = "0007_relationship_rules"
down_revision = "0006_roles"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0007_relationship_rules.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        ALTER TABLE core.validation_rules DROP CONSTRAINT IF EXISTS validation_rules_relationship_rule;
        DELETE FROM core.validation_rules WHERE rule_type_code = 'has_relationship';
        ALTER TABLE core.validation_rules DROP CONSTRAINT IF EXISTS validation_rules_field_name_check;
        ALTER TABLE core.validation_rules ADD CONSTRAINT validation_rules_field_name_check
            CHECK (field_name IN ('name', 'description', 'display_id'));
        DELETE FROM core.rule_types WHERE code = 'has_relationship';
        UPDATE core.schema_versions SET description = replace(description, '; rules that an entity has a relationship (0007)', '')
         WHERE version = '0.3.1';
        """
    )
