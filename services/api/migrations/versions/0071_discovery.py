"""Data discovery and ingestion (the Release 3 epic, D670): import sources that are OData feeds read by EA Explorer,
endpoints pushed to, or an AI reading documents; what each delivered last; matches a person confirmed. No version change.

Revision ID: 0071_discovery
Revises: 0070_text_keys
Create Date: 2026-11-13

The SQL lives in migrations/sql/0071_discovery.sql.
"""

from pathlib import Path

from alembic import op

revision = "0071_discovery"
down_revision = "0070_text_keys"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0071_discovery.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DROP TABLE IF EXISTS core.discovery_matches; DROP TABLE IF EXISTS core.discovery_seen;
                   ALTER TABLE core.loads DROP CONSTRAINT IF EXISTS loads_delivery_check;
                   ALTER TABLE core.loads ADD CONSTRAINT loads_delivery_check CHECK (delivery IN ('upload', 'folder', 'api'));
                   DROP INDEX IF EXISTS core.import_sources_due_idx;
                   ALTER TABLE core.import_sources DROP COLUMN IF EXISTS kind, DROP COLUMN IF EXISTS url,
                       DROP COLUMN IF EXISTS auth_ref, DROP COLUMN IF EXISTS mapping, DROP COLUMN IF EXISTS schedule,
                       DROP COLUMN IF EXISTS next_run_at, DROP COLUMN IF EXISTS last_run""")
