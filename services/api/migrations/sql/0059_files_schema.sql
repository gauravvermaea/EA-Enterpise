-- =====================================================================================
-- 0059_files_schema: the file store for a platform with no local file system (R2.44, D635; owner, 12 Nov 2026, 21:28:
--   "users should be able to work on local file system, but purely serverless docker environment uses a separate DB";
--   13 Nov 2026: schemas only). One setting, EAX_FILE_STORE, chooses: folder (the work folder, as today, the default)
--   or database (this schema, reached by EAX_FILES_DB_URL, empty = this database). The self-test's reports,
--   screenshots, videos and logs and the exports go through it. Backups never do (owner, 21:47). No version change.
-- =====================================================================================

CREATE SCHEMA IF NOT EXISTS files;

CREATE TABLE IF NOT EXISTS files.store (
    area        text        NOT NULL CHECK (area ~ '^[a-z][a-z0-9_-]{0,39}$'),
    name        text        NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 500 AND name !~ '(^|/)\.\.(/|$)'),
    content     bytea       NOT NULL,
    bytes       bigint      NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (area, name)
);
CREATE INDEX IF NOT EXISTS store_area_time ON files.store (area, modified_at DESC);
COMMENT ON TABLE files.store IS 'R2.44: files kept in the database when EAX_FILE_STORE=database (no local file system)';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_app') THEN
        GRANT USAGE ON SCHEMA files TO eax_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON files.store TO eax_app;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT USAGE ON SCHEMA files TO eax_migrator;
        GRANT SELECT, INSERT, UPDATE, DELETE ON files.store TO eax_migrator;
    END IF;
END;
$$;
