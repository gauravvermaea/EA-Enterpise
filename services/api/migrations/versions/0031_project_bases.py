"""Phase 13.1 (version 0.15.0): project bases, standards, governance log, charter (D303 to D307).

Revision ID: 0031_project_bases
Revises: 0030_reference_library
Create Date: 2026-11-08

The SQL lives in migrations/sql/0031_project_bases.sql (checked by tests/test_project_bases.py).
"""

from pathlib import Path

from alembic import op

revision = "0031_project_bases"
down_revision = "0030_reference_library"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0031_project_bases.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0031 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""ALTER TABLE proj.projects DROP COLUMN completed_at, DROP COLUMN completed_by;
                   DROP TABLE IF EXISTS proj.phase_states;
                   UPDATE proj.documents SET kind = NULL WHERE kind = 'None';
                   ALTER TABLE proj.documents DROP CONSTRAINT documents_kind_check;
                   ALTER TABLE proj.documents ADD CONSTRAINT documents_kind_check CHECK (kind IN ('Deliverable', 'Artifact'));
                   ALTER TABLE proj.documents DROP COLUMN title;
                   ALTER TABLE proj.org_people DROP COLUMN skills;
                   DROP TABLE IF EXISTS proj.charters;
                   DROP TABLE IF EXISTS proj.gov_kinds;
                   DROP TABLE IF EXISTS proj.gov_records;
                   DROP TABLE IF EXISTS proj.base_skips;
                   DROP TABLE IF EXISTS proj.standards;
                   ALTER TABLE proj.steps DROP COLUMN guid, DROP COLUMN origin_guid;
                   ALTER TABLE proj.principles DROP COLUMN guid, DROP COLUMN origin_guid, DROP COLUMN mandatory, DROP COLUMN sort_order;
                   ALTER TABLE proj.projects DROP COLUMN base_kind, DROP COLUMN base_id;
                   DELETE FROM core.schema_versions WHERE version = '0.15.0'""")
