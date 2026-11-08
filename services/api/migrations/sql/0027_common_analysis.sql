-- =====================================================================================
-- 0027_common_analysis: build phase 13.0.5 (version 0.14.5), common analysis (D286)
--   * what two or more models (each as it is now or a tag) have in common, stored in a project model the person
--     chooses (its roles decide who sees and works on it, as for gap analyses, D177), with numbered runs
-- Rows only: the matching, the threshold and the rules are in eax/commons.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.14.5', '0027_common_analysis', 'Phase 13.0.5: common analysis (what models have in common)');

CREATE TABLE core.common_analyses (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid          uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id      bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,   -- stored in: its roles decide access
    name          text NOT NULL CHECK (btrim(name) <> ''),
    description   text NOT NULL DEFAULT '',
    sides         jsonb NOT NULL,               -- [{kind, model_id, model, tag_id, tag, commit, label, request}]
    settings      jsonb NOT NULL DEFAULT '{}',  -- {threshold, types, relationship_types, values, relationships, matches, rejected}
    summary       jsonb NOT NULL DEFAULT '{}',
    relationships jsonb NOT NULL DEFAULT '[]',  -- the relationships of the last run, with the sides that have each
    suggestions   jsonb NOT NULL DEFAULT '[]',  -- close names to confirm or reject
    runs_made     integer NOT NULL DEFAULT 0,
    compared_at   timestamptz NOT NULL DEFAULT now(),
    compared_by   text NOT NULL,
    created_by    text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX common_analyses_name_idx ON core.common_analyses (model_id, lower(name));
COMMENT ON TABLE core.common_analyses IS 'A common analysis: what two or more models have in common (D286)';

CREATE TABLE core.common_items (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid             uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    analysis_id      bigint NOT NULL REFERENCES core.common_analyses (id) ON DELETE CASCADE,
    match_key        text NOT NULL,                  -- its members, side:guid joined: notes follow a member when compared again
    entity_type      text NOT NULL,
    entity_type_name text NOT NULL DEFAULT '',
    layer            text NOT NULL DEFAULT '',
    name             text NOT NULL,
    members          jsonb NOT NULL DEFAULT '{}',    -- {side index: {guid, name, display_id}}
    sides_count      integer NOT NULL DEFAULT 1,
    is_common        boolean NOT NULL DEFAULT false, -- in at least the threshold's number of sides
    differs          jsonb NOT NULL DEFAULT '[]',    -- [{field, label, values: {side index: value}}]
    note             text NOT NULL DEFAULT '',
    decision         text NOT NULL DEFAULT '',
    gone             boolean NOT NULL DEFAULT false,
    modified_by      text,
    modified_at      timestamptz,
    UNIQUE (analysis_id, match_key)
);
CREATE INDEX common_items_analysis_idx ON core.common_items (analysis_id, is_common);
COMMENT ON TABLE core.common_items IS 'One element of a common analysis: which sides have it, what differs, its note and decision';

CREATE TABLE core.common_runs (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    analysis_id  bigint NOT NULL REFERENCES core.common_analyses (id) ON DELETE CASCADE,
    number       integer NOT NULL,
    compared_at  timestamptz NOT NULL DEFAULT now(),
    compared_by  text NOT NULL,
    sides        jsonb NOT NULL,
    totals       jsonb NOT NULL DEFAULT '{}',
    items        jsonb NOT NULL DEFAULT '[]',
    UNIQUE (analysis_id, number)
);
COMMENT ON TABLE core.common_runs IS 'Each result of a common analysis (made or compared again)';
