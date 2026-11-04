"""Phase 6 (version 0.6.0): data entry in forms: tags, rule overrides (D48), relationships outside the metamodel (D49).

Revision ID: 0010_data_entry
Revises: 0009_reports
Create Date: 2026-11-04

The SQL lives in migrations/sql/0010_data_entry.sql (checked by tests/sql/phase6_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0010_data_entry"
down_revision = "0009_reports"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0010_data_entry.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0010 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DROP VIEW IF EXISTS rpt.entity_tags;
        DROP FUNCTION IF EXISTS rpt.f_entity_tags(), core.allow_from_content(bigint, bigint, bigint, bigint);
        DROP TRIGGER IF EXISTS entities_3_tags ON core.entities;
        DROP TRIGGER IF EXISTS entities_3a_copy_tags ON core.entities;
        DROP FUNCTION IF EXISTS core.clean_tags(), core.copy_tags();
        ALTER TABLE core.allowed_relationships DROP COLUMN IF EXISTS from_content;
        ALTER TABLE core.attribute_values DROP COLUMN IF EXISTS rule_override;
        ALTER TABLE core.entities DROP COLUMN IF EXISTS tags;
        DELETE FROM core.schema_versions WHERE version = '0.6.0';
        """
    )
