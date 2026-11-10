-- =====================================================================================
-- 0001_library: the library service's own database (phase 15.2, owner, 9 Nov 2026, D346 to D350)
--   * one organisation (enterprise) library and a library per project
--   * a folder tree of any shape in each; entries are pages (simple blocks: headings, text, lists, tables, links),
--     links (to a web address or into EA Explorer: a model, project, entity, view, document, page) and the
--     occasional uploaded file (kept here, for search)
--   * every change kept with its before and after, so it can be undone (light moderation: changes show at once)
-- Rows only: the rules are in libsvc/library.py (D248).
-- =====================================================================================

CREATE SCHEMA IF NOT EXISTS lib;

CREATE TABLE lib.schema_versions (
    version     text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lib.libraries (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid          uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    scope         text NOT NULL CHECK (scope IN ('org', 'project')),
    project_guid  uuid UNIQUE,                         -- the project's id in EA Explorer (no foreign key: another database)
    project_name  text NOT NULL DEFAULT '',            -- kept in step when the project is opened
    in_enterprise boolean NOT NULL DEFAULT false,      -- a project library shown in the enterprise library, read only
    external_link text NOT NULL DEFAULT '',            -- a project's own library somewhere else (its Library tab opens it)
    created_by    text NOT NULL DEFAULT 'system',
    created_at    timestamptz NOT NULL DEFAULT now(),
    CHECK ((scope = 'org') = (project_guid IS NULL))
);
CREATE UNIQUE INDEX libraries_one_org ON lib.libraries (scope) WHERE scope = 'org';

CREATE TABLE lib.folders (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    library_id  bigint NOT NULL REFERENCES lib.libraries (id) ON DELETE CASCADE,
    parent_id   bigint REFERENCES lib.folders (id) ON DELETE CASCADE,
    name        text NOT NULL,
    sort_order  integer NOT NULL DEFAULT 0,
    is_deleted  boolean NOT NULL DEFAULT false,
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX folders_library ON lib.folders (library_id, parent_id);

CREATE TABLE lib.entries (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    library_id   bigint NOT NULL REFERENCES lib.libraries (id) ON DELETE CASCADE,
    folder_id    bigint REFERENCES lib.folders (id) ON DELETE SET NULL,    -- NULL: the top of the library
    kind         text NOT NULL CHECK (kind IN ('page', 'link', 'file')),
    title        text NOT NULL,
    description  text NOT NULL DEFAULT '',
    tags         text[] NOT NULL DEFAULT '{}',
    blocks       jsonb NOT NULL DEFAULT '[]',          -- a page: [{type, ...}]
    href         text NOT NULL DEFAULT '',             -- a link: https://..., or ea:<kind>:<ids>
    file_name    text NOT NULL DEFAULT '',
    content_type text NOT NULL DEFAULT '',
    content      bytea,
    file_size    bigint NOT NULL DEFAULT 0,
    search_doc   text NOT NULL DEFAULT '',             -- what search reads: title, description, tags, the text, link names, file text
    sort_order   integer NOT NULL DEFAULT 0,
    is_deleted   boolean NOT NULL DEFAULT false,
    editing_by   text NOT NULL DEFAULT '',             -- a page held while someone edits it
    editing_at   timestamptz,
    created_by   text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    changed_by   text NOT NULL DEFAULT '',
    changed_at   timestamptz
);
CREATE INDEX entries_folder ON lib.entries (library_id, folder_id) WHERE NOT is_deleted;
CREATE INDEX entries_search ON lib.entries USING gin (to_tsvector('simple', search_doc));
CREATE INDEX entries_trgm ON lib.entries USING gin (search_doc gin_trgm_ops);

-- every change: what it was before and after (a page's blocks, a link, a folder), so it can be undone
CREATE TABLE lib.changes (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    library_id  bigint NOT NULL REFERENCES lib.libraries (id) ON DELETE CASCADE,
    entry_id    bigint REFERENCES lib.entries (id) ON DELETE CASCADE,
    folder_id   bigint REFERENCES lib.folders (id) ON DELETE CASCADE,
    action      text NOT NULL,                         -- added, changed, moved, removed, undone
    title       text NOT NULL DEFAULT '',
    before      jsonb,
    after       jsonb,
    undone_by   text NOT NULL DEFAULT '',
    username    text NOT NULL,
    at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX changes_library ON lib.changes (library_id, at DESC);

INSERT INTO lib.libraries (scope) VALUES ('org');
INSERT INTO lib.schema_versions (version) VALUES ('0001_library');
