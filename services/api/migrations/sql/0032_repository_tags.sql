-- =====================================================================================
-- 0032_repository_tags: version 0.15.1, the project's documents table (owner, 8 Nov 2026, D312)
--   * a tag on the whole repository: the version of every document at that moment, to download them all as they
--     were, or to bring the repository back to the tag (a tag "before application of tag <name>" is made first)
--   * templates added to a document class to download (apart from the ones its documents were made from)
--   * the template a document was copied from
-- Rows only: the rules are in eax/repo_tags.py and eax/projects.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.15.1', '0032_repository_tags', 'Repository tags; templates added to a document class');

CREATE TABLE proj.repo_tags (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    name        text NOT NULL,
    note        text NOT NULL DEFAULT '',
    auto        boolean NOT NULL DEFAULT false,     -- made by a revert: "before application of tag <name>"
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, name)
);

-- each document at the tag: its version then, and whether it was archived then
CREATE TABLE proj.repo_tag_docs (
    tag_id       bigint NOT NULL REFERENCES proj.repo_tags (id) ON DELETE CASCADE,
    document_id  bigint NOT NULL REFERENCES proj.documents (id) ON DELETE CASCADE,
    version      integer NOT NULL,
    user_version text NOT NULL DEFAULT '',
    file_name    text NOT NULL DEFAULT '',
    title        text NOT NULL DEFAULT '',
    archived     boolean NOT NULL DEFAULT false,
    PRIMARY KEY (tag_id, document_id)
);

ALTER TABLE proj.items ADD COLUMN offered_templates bigint[] NOT NULL DEFAULT '{}';

-- the template a document was copied from: the repository build copies each template once, whatever the copy's file is
-- called after a check-in (review, 8 Nov 2026)
ALTER TABLE proj.documents ADD COLUMN template_id bigint;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;
