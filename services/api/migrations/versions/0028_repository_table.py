"""Phase 13.0.6 (version 0.14.6): the project repository as a table (D290).

Revision ID: 0028_repository_table
Revises: 0027_common_analysis
Create Date: 2026-11-07

The SQL lives in migrations/sql/0028_repository_table.sql (checked by tests/test_projects.py).
"""

from pathlib import Path

from alembic import op

revision = "0028_repository_table"
down_revision = "0027_common_analysis"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection  # the psycopg 3 connection
    raw.execute((SQL_DIR / "0028_repository_table.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Clean rebuilds are the rule (D54); this removes what 0028 added.
    raw = op.get_bind().connection.driver_connection
    raw.execute("""DELETE FROM core.favourites WHERE kind = 'project';
                   ALTER TABLE core.favourites DROP CONSTRAINT favourites_kind_check;
                   ALTER TABLE core.favourites ADD CONSTRAINT favourites_kind_check CHECK (kind IN ('entity', 'model', 'view'));
                   ALTER TABLE proj.principles DROP COLUMN area;
                   DROP TABLE IF EXISTS proj.task_statuses;
                   DROP TABLE IF EXISTS proj.tasks;
                   ALTER TABLE proj.documents DROP COLUMN link_url, DROP COLUMN link_project, DROP COLUMN link_document,
                       DROP COLUMN link_item, DROP COLUMN description;
                   ALTER TABLE proj.projects DROP COLUMN is_library;
                   DROP TABLE IF EXISTS proj.stakeholder_notes;
                   DROP TABLE IF EXISTS proj.stakeholders;
                   ALTER TABLE proj.project_viewpoints DROP COLUMN phase;
                   ALTER TABLE proj.projects DROP COLUMN repo_started_at;
                   ALTER TABLE proj.projects DROP COLUMN repo_again;
                   ALTER TABLE proj.items DROP COLUMN mayan_cabinet_chosen;
                   DELETE FROM proj.steps WHERE parent_step_id IS NOT NULL;
                   ALTER TABLE proj.steps DROP COLUMN parent_step_id, DROP COLUMN added_by, DROP COLUMN added_at, DROP COLUMN due_date;
                   ALTER TABLE core.models DROP COLUMN source_tag_id, DROP COLUMN source_tag_name;
                   ALTER TABLE proj.signoff_requests DROP COLUMN quorum;
                   ALTER TABLE proj.projects DROP COLUMN signoff_quorum, DROP COLUMN sponsor_notes_html, DROP COLUMN goals_notes_html;
                   DROP INDEX IF EXISTS proj.documents_live;
                   UPDATE proj.documents SET state = 'Approved' WHERE state = 'Accepted';
                   ALTER TABLE proj.documents DROP CONSTRAINT documents_state_check,
                       ADD CONSTRAINT documents_state_check CHECK (state IN ('Draft', 'In review', 'Approved', 'Rejected', 'Superseded',
                                                                             'Withdrawn', 'Not for use'));
                   ALTER TABLE proj.items DROP COLUMN not_needed_reason, DROP COLUMN not_needed_by, DROP COLUMN not_needed_at,
                       DROP COLUMN added_by;
                   ALTER TABLE proj.document_events DROP COLUMN user_version;
                   ALTER TABLE proj.documents DROP COLUMN user_version, DROP COLUMN out_version, DROP COLUMN tags,
                       DROP COLUMN accepted_by, DROP COLUMN accepted_at, DROP COLUMN accepted_note, DROP COLUMN accepted_evidence,
                       DROP COLUMN archived_by, DROP COLUMN archived_at, DROP COLUMN deleted_by, DROP COLUMN deleted_at;
                   DELETE FROM core.schema_versions WHERE version = '0.14.6'""")
