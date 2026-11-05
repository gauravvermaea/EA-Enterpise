-- =====================================================================================
-- 0017_sheets: build phase 10.1 (version 0.10.1), import and export sheets (D77, D78, D88, D197)
--   * core.loads: an uploaded sheet (Excel or CSV), its preview, and the changes it became (the uploader's own
--     uncommitted changes, D165); undone as a whole
--   * core.column_mappings: headers of other systems' sheets mapped to attributes, saved for reuse
--   (collection sets, feeds and scheduled exports are a phase of their own, designed first: D198)
--   * core.task_files: files a background task made (a downloaded sheet), fetched once it is done
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.10.1', '0017_sheets', 'Phase 10.1: import and export sheets, loads, column mappings');

CREATE TABLE core.task_files (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id      bigint NOT NULL REFERENCES core.tasks (id) ON DELETE CASCADE,
    name         text NOT NULL,
    content_type text NOT NULL,
    content      bytea NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX task_files_task_idx ON core.task_files (task_id);

CREATE TABLE core.column_mappings (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid           uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id       bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    name           text NOT NULL CHECK (btrim(name) <> ''),
    entity_type_id bigint REFERENCES core.entity_types (id) ON DELETE CASCADE,
    columns        jsonb NOT NULL DEFAULT '{}',     -- {header in the file: field or attribute code, or "" to ignore}
    created_by     text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX column_mappings_name_idx ON core.column_mappings (model_id, lower(name));
COMMENT ON TABLE core.column_mappings IS 'Phase 10.1: headers of sheets from other systems mapped to attributes, saved for reuse';


CREATE TABLE core.loads (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid           uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id       bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    file_name      text NOT NULL,
    format         text NOT NULL,                 -- xlsx, xlsm, csv, zip (a CSV set)
    content        bytea NOT NULL,
    status         text NOT NULL DEFAULT 'uploaded'
                   CHECK (status IN ('uploaded', 'mapping', 'previewed', 'added', 'undone', 'failed')),
    message        text NOT NULL DEFAULT '',
    mapping        jsonb NOT NULL DEFAULT '{}',   -- {sheet: {entity_type, columns {header: code}}} for unknown headers
    preview        jsonb NOT NULL DEFAULT '{}',   -- rows with what each would do; edited on screen before it is added
    summary        jsonb NOT NULL DEFAULT '{}',
    change_ids     uuid[] NOT NULL DEFAULT '{}',   -- the uncommitted changes it became (core.pending_changes.guid)
    owner          text NOT NULL,                 -- whose changes it becomes: the uploader
    created_by     text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    added_at       timestamptz,
    undone_at      timestamptz,
    undone_by      text
);
CREATE INDEX loads_model_idx ON core.loads (model_id, created_at DESC);
COMMENT ON TABLE core.loads IS 'Phase 10.1: an uploaded sheet, its preview and the uncommitted changes it became (D197)';

-- where an uncommitted change came from (owner, 5 Nov 2026): "Load of <file>" for the rows of a loaded sheet; shown on the
-- Changes tab and, once committed, with the commit on the History tab
ALTER TABLE core.pending_changes ADD COLUMN source text;
