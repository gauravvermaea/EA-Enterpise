"""Phase 1: metamodel and generic repository content, history, and the get_entity functions.

Revision ID: 0002_metamodel
Revises: 0001_foundation
Create Date: 2026-11-03

The SQL lives in migrations/sql/ as plain files (tested directly against PostgreSQL):
    0002_metamodel.sql   tables, integrity triggers, history
    0002_functions.sql   eax.get_entity and eax.get_entity_by_name
They contain PL/pgSQL bodies, so each file is sent to the server as one script through the
psycopg connection (no parameters, so several statements and $$ quoting are fine).
"""

from pathlib import Path

from alembic import op

revision = "0002_metamodel"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _run_script(name: str) -> None:
    script = (SQL_DIR / name).read_text(encoding="utf-8")
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute(script)


def upgrade() -> None:
    _run_script("0002_metamodel.sql")
    _run_script("0002_functions.sql")


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DROP SCHEMA IF EXISTS eax CASCADE;
        DROP TABLE IF EXISTS core.attribute_value, core.relationship, core.entity,
            core.display_id_counter, core.allowed_relationship, core.validation_rule,
            core.item_attribute, core.attribute_type, core.pick_list_value, core.pick_list,
            core.relationship_type, core.entity_type, core.layer, core.model,
            core.rule_type, core.data_type, core.model_kind, core.item_status CASCADE;
        DROP TABLE IF EXISTS history.row_versions CASCADE;
        DROP FUNCTION IF EXISTS core.current_actor(), core.stamp_row(), core.can_read_model(uuid),
            core.check_entity(), core.check_relationship(), core.check_attribute_value(),
            history.capture(), history.refuse_change() CASCADE;
        """
    )
