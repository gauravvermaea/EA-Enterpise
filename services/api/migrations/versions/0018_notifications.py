"""Phase 8.1 (version 0.11.0): notifications, requests, webhooks, metamodel push-down, change documents (D209).

Revision ID: 0018_notifications
Revises: 0017_sheets
Create Date: 2026-11-06

The SQL lives in migrations/sql/0018_notifications.sql (checked by tests/sql/phase8_1_checks.sql).
"""

from pathlib import Path

from alembic import op

revision = "0018_notifications"
down_revision = "0017_sheets"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0018_notifications.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0018 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute(
        """
        DROP VIEW IF EXISTS core.metamodel_versions_pushed;
        DROP TABLE IF EXISTS core.change_documents, core.metamodel_push_targets, core.metamodel_pushes,
            core.metamodel_version_changes, core.webhook_deliveries, core.webhooks, core.request_comments, core.requests,
            core.notification_recipients, core.notifications;
        DELETE FROM core.schema_versions WHERE version = '0.11.0';
        """
    )
