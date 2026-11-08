-- =====================================================================================
-- 0030_reference_library: build phase 13.0.8 (version 0.14.8), the organisation's reference library (D300)
--   * one library for the whole organisation, beside each project's own Reference area: documents and links
--   * a free folder tree; each entry has a title, a description, its source, tags
--   * every file kept by version (each version its own document in the document store)
--   * the text inside documents kept for search (read out of the file by the application, not the database)
--   * everyone signed in reads it; Super Admins change it; a project links to an entry from its Reference area
-- Rows only: the rules are in eax/reference_library.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.14.8', '0030_reference_library', 'Phase 13.0.8: the organisation''s reference library');

CREATE TABLE proj.org_ref_folders (
    path        text PRIMARY KEY,                          -- e.g. Standards/Security
    description text NOT NULL DEFAULT '',
    added_by    text NOT NULL,
    added_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE proj.org_ref_entries (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid              uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    folder            text NOT NULL DEFAULT '',            -- '' is the top of the library
    kind              text NOT NULL CHECK (kind IN ('file', 'link')),
    title             text NOT NULL,
    description       text NOT NULL DEFAULT '',
    source            text NOT NULL DEFAULT '',            -- who publishes it (a standards body, a regulator, a team)
    tags              text[] NOT NULL DEFAULT '{}',
    link_url          text NOT NULL DEFAULT '',            -- a link: its web address
    file_name         text NOT NULL DEFAULT '',            -- a file: its current version's name
    mayan_document_id bigint,                              -- a file: its current version in the document store
    version           integer NOT NULL DEFAULT 0,
    search_text       text NOT NULL DEFAULT '',            -- the text read out of the current file, for search
    created_by        text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    modified_by       text,
    modified_at       timestamptz
);
CREATE INDEX org_ref_entries_folder ON proj.org_ref_entries (folder, title);
CREATE INDEX org_ref_entries_tags ON proj.org_ref_entries USING gin (tags);
CREATE INDEX org_ref_entries_search ON proj.org_ref_entries
    USING gin (to_tsvector('english', title || ' ' || description || ' ' || source || ' ' || search_text));

CREATE TABLE proj.org_ref_versions (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entry_id          bigint NOT NULL REFERENCES proj.org_ref_entries (id) ON DELETE CASCADE,
    version           integer NOT NULL,
    file_name         text NOT NULL,
    size_bytes        bigint NOT NULL DEFAULT 0,
    mayan_document_id bigint,
    note              text NOT NULL DEFAULT '',
    by_user           text NOT NULL,
    at                timestamptz NOT NULL DEFAULT now(),
    UNIQUE (entry_id, version)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;
