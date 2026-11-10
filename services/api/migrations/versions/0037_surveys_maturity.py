"""Version 0.17.0: surveys (phase 38.1) and EA capability maturity (phase 40).

Revision ID: 0037_surveys_maturity
Revises: 0036_machine_access_ops
Create Date: 2026-11-10

The SQL lives in migrations/sql/0037_surveys_maturity.sql (checked by tests/test_surveys.py).
"""

from pathlib import Path

from alembic import op

revision = "0037_surveys_maturity"
down_revision = "0036_machine_access_ops"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0037_surveys_maturity.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0037 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DROP TABLE IF EXISTS core.survey_responses;
                   DROP TABLE IF EXISTS core.survey_recipients;
                   DROP TABLE IF EXISTS core.surveys""")
