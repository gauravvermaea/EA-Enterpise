-- =====================================================================================
-- 0046_industry_packs: version 0.19.0, the industry packs' files (phase 39, owner 10 Nov 2026, D546 to D551)
--   * an industry pack file: one file of an industry starter pack (the book, the workbook, the metamodel Excel to study,
--     the Excel templates, the PowerPoints, the read-me, the worked example's views), stored in Documents (Mayan) and
--     downloaded from the pack's tiles in the library. Loaded by `eax packs load` or System admin from a folder; the
--     checksum says whether a file changed (a changed file is a new version in Mayan, an unchanged one is skipped)
-- Rows only (D248): classifying, the AI-use check and the loading are in eax/industry_packs.py.
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.19.0', '0046_industry_packs', 'The last set: the industry packs'' files in Documents')
ON CONFLICT (version) DO NOTHING;   -- several 0.19.0 migrations: the first one writes the version

CREATE TABLE core.industry_pack_files (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid              uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    industry          text NOT NULL CHECK (industry ~ '^[a-z][a-z0-9-]{1,40}$'),     -- banking, healthcare, insurance...
    kind              text NOT NULL CHECK (kind IN ('readme', 'book', 'workbook', 'metamodel', 'metamodel_template',
                                                    'template', 'powerpoint', 'example_views')),
    title             text NOT NULL CHECK (btrim(title) <> '' AND length(title) <= 300),
    file_name         text NOT NULL CHECK (btrim(file_name) <> '' AND length(file_name) <= 250),
    content_type      text NOT NULL DEFAULT 'application/octet-stream',
    file_size         bigint NOT NULL CHECK (file_size >= 0),
    checksum          text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),                -- sha256 of the file
    mayan_document_id bigint,                                                          -- null: kept here only (sample, no Documents)
    versions          integer NOT NULL DEFAULT 1 CHECK (versions >= 1),
    sample            boolean NOT NULL DEFAULT false,                                  -- a stand-in file from the sample data
    sample_content    bytea,                                                           -- only for sample stand-ins (tiny)
    loaded_by         text NOT NULL,
    loaded_at         timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (industry, file_name)
);
CREATE INDEX industry_pack_files_industry ON core.industry_pack_files (industry, kind);
COMMENT ON TABLE core.industry_pack_files IS 'Phase 39: the industry packs'' files (book, workbook, metamodel Excel, templates, PowerPoints) in Documents (D546)';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.industry_pack_files TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
END;
$$;
