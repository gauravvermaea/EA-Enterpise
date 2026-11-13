-- =====================================================================================
-- 0053_archive_store: archived and deleted models and projects (R2.41, D626; owner, 12 Nov 2026)
--   A model or project that is archived or deleted is taken out of the working database whole, as its backup file (the
--   deep package with its history; a project with its documents), into the archive database (EAX_ARCHIVE_DB_URL,
--   R2.50: empty = this database, the table below; otherwise the same table there, made at start by
--   eax.databases ensure). Deleted ones are kept until a Super Admin purges them. Rows only (D248); no version change.
-- =====================================================================================

CREATE TABLE IF NOT EXISTS core.archive_store (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind         text        NOT NULL CHECK (kind IN ('model', 'project')),
    state        text        NOT NULL CHECK (state IN ('archived', 'deleted')),
    guid         uuid        NOT NULL,
    name         text        NOT NULL CHECK (length(name) <= 400),
    summary      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    admins       text[]      NOT NULL DEFAULT '{}',
    file         bytea       NOT NULL,
    file_bytes   bigint      NOT NULL DEFAULT 0,
    note         text        NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
    moved_at     timestamptz NOT NULL DEFAULT now(),
    moved_by     text        NOT NULL,
    UNIQUE (kind, guid)
);
CREATE INDEX IF NOT EXISTS archive_store_listing ON core.archive_store (kind, state, moved_at DESC);
COMMENT ON TABLE core.archive_store IS 'R2.41: archived and deleted models and projects, each as its backup file, in the archive database';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.archive_store TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
END;
$$;
