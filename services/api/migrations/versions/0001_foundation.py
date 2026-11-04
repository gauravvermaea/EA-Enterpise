"""Phase 0 foundation: schemas, append-only audit log, staging skeleton, sample report view.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-11-03

Each statement is run on its own: the database driver does not accept several statements
in one call.
"""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = ["library", "core", "staging", "history", "audit", "jobs", "rpt"]

UPGRADE = [
    # ---- Audit log: append-only; updates, deletes and truncates are refused by triggers
    """
    CREATE TABLE audit.events (
        id          bigserial PRIMARY KEY,
        at          timestamptz NOT NULL DEFAULT now(),
        actor       text        NOT NULL,
        action      text        NOT NULL,
        object_type text,
        object_id   text,
        model_id    uuid,
        details     jsonb       NOT NULL DEFAULT '{}'::jsonb,
        source      text        NOT NULL DEFAULT 'api',
        request_id  text
    )
    """,
    "CREATE INDEX events_at_idx ON audit.events (at DESC)",
    "CREATE INDEX events_object_idx ON audit.events (object_type, object_id)",
    """
    CREATE FUNCTION audit.refuse_change() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION USING MESSAGE = 'audit.events is append-only: ' || TG_OP || ' refused';
    END;
    $$
    """,
    """
    CREATE TRIGGER events_no_update BEFORE UPDATE OR DELETE ON audit.events
        FOR EACH ROW EXECUTE FUNCTION audit.refuse_change()
    """,
    """
    CREATE TRIGGER events_no_truncate BEFORE TRUNCATE ON audit.events
        FOR EACH STATEMENT EXECUTE FUNCTION audit.refuse_change()
    """,
    # ---- Staging and publishing workflow: skeleton only (filled in build phase 8)
    """
    CREATE TABLE staging.change_sets (
        id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id     uuid,
        source       text NOT NULL CHECK (source IN
                     ('web','csv','diagram','mcp','merge','survey','exchange','dedupe','feed')),
        status       text NOT NULL DEFAULT 'draft' CHECK (status IN
                     ('draft','submitted','approved','rejected','published','abandoned')),
        title        text,
        created_by   text NOT NULL,
        created_at   timestamptz NOT NULL DEFAULT now(),
        submitted_at timestamptz,
        decided_by   text,
        decided_at   timestamptz,
        published_at timestamptz,
        comment      text
    )
    """,
    """
    CREATE TABLE staging.change_items (
        id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        change_set_id  uuid NOT NULL REFERENCES staging.change_sets(id) ON DELETE CASCADE,
        seq            integer NOT NULL,
        operation      text NOT NULL CHECK (operation IN
                       ('create','update','retire','restore','delete','relate','unrelate')),
        object_type    text NOT NULL,
        object_id      uuid,
        payload        jsonb NOT NULL DEFAULT '{}'::jsonb,
        status         text NOT NULL DEFAULT 'pending' CHECK (status IN
                       ('pending','approved','rejected','published','error')),
        error          text,
        review_comment text,
        UNIQUE (change_set_id, seq)
    )
    """,
    # ---- Phase 0 sample data and the first report view (read by Superset)
    """
    CREATE TABLE core.heartbeat_logs (
        id           bigserial PRIMARY KEY,
        at           timestamptz NOT NULL DEFAULT now(),
        source       text NOT NULL,
        note         text NOT NULL DEFAULT '',
        requested_by text NOT NULL,
        job_id       bigint
    )
    """,
    """
    INSERT INTO core.heartbeat_logs (source, note, requested_by)
    VALUES ('setup', 'First heartbeat, written by the first migration', 'system')
    """,
    """
    CREATE VIEW rpt.v_heartbeat AS
        SELECT id, at, date_trunc('day', at) AS day, source, note, requested_by, job_id
        FROM core.heartbeat_logs
    """,
    # ---- The read-only report login may read the rpt schema and nothing else
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
            GRANT USAGE ON SCHEMA rpt TO eax_report;
            GRANT SELECT ON ALL TABLES IN SCHEMA rpt TO eax_report;
            ALTER DEFAULT PRIVILEGES IN SCHEMA rpt GRANT SELECT ON TABLES TO eax_report;
        END IF;
    END
    $$
    """,
]

DOWNGRADE = [
    "DROP VIEW IF EXISTS rpt.v_heartbeat",
    "DROP TABLE IF EXISTS core.heartbeat_logs",
    "DROP TABLE IF EXISTS staging.change_items",
    "DROP TABLE IF EXISTS staging.change_sets",
    "DROP TABLE IF EXISTS audit.events",
    "DROP FUNCTION IF EXISTS audit.refuse_change()",
]


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
