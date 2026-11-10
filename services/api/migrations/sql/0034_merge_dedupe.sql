-- =====================================================================================
-- 0034_merge_dedupe: version 0.17.0, batch 1 (D421): merging a child into its parent (phases 19 and 20, D359, D422 to
-- D425) and dedupe within a model (phase 21, D361, D426 to D428)
--   * a child model's starting point: a tag of kind 'start', taken when the child is made from its parent and again when
--     it is refreshed from it; the three-way review compares against it
--   * merge requests: a child sent to its parent for merge, the changes found (three-way), each reviewer's decision
--     with its reason, the merge report, and what was done with the child afterwards (frozen or refreshed)
--   * entity aliases: when duplicates are merged, the removed entities' guids and display IDs keep finding the one kept
-- Rows only: the rules are in eax/merge_back.py and eax/dedupe.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.17.0', '0034_merge_dedupe', 'Batch 1 (D421): merge a child into its parent; dedupe within a model')
ON CONFLICT (version) DO NOTHING;   -- several 0.17.0 migrations (batch 1): the first one writes the version

-- a child's starting point is a tag of its own kind (D423)
ALTER TABLE core.model_tags DROP CONSTRAINT IF EXISTS model_tags_kind_check;
ALTER TABLE core.model_tags ADD CONSTRAINT model_tags_kind_check
    CHECK (kind IN ('manual', 'before-restore', 'backup', 'start'));

-- ---------------------------------------------------------------- merge requests (phases 19 and 20)
CREATE TABLE core.merge_requests (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    number       integer NOT NULL,                                -- per parent: merge request 1, 2, ...
    child_id     bigint NOT NULL REFERENCES core.models (id),
    parent_id    bigint NOT NULL REFERENCES core.models (id),
    status       text NOT NULL DEFAULT 'sent'
                 CHECK (status IN ('sent', 'merged', 'closed', 'withdrawn')),
    note         text NOT NULL DEFAULT '',                        -- the sender's note to the reviewers
    base_tag_id  bigint REFERENCES core.model_tags (id),          -- the child's starting point (empty: none, every difference asked)
    plan         jsonb NOT NULL,                                  -- the changes found, three-way (eax.merge_back.plan)
    decisions    jsonb NOT NULL DEFAULT '{}'::jsonb,              -- {change id: {accept, reason, by, at}}
    report       jsonb,                                           -- accepted, rejected with reasons, failed; the commit
    after        text NOT NULL DEFAULT '' CHECK (after IN ('', 'frozen', 'refreshed')),
    sent_by      text NOT NULL,
    sent_at      timestamptz NOT NULL DEFAULT now(),
    merged_by    text,
    merged_at    timestamptz,
    closed_by    text,
    closed_at    timestamptz,
    UNIQUE (parent_id, number)
);
CREATE INDEX merge_requests_child_idx ON core.merge_requests (child_id, status);
CREATE INDEX merge_requests_parent_idx ON core.merge_requests (parent_id, status);
COMMENT ON TABLE core.merge_requests IS 'A child model sent to its parent for merge (D359): three-way changes, decisions, the report';

-- ---------------------------------------------------------------- entity aliases (phase 21)
CREATE TABLE core.entity_aliases (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id        bigint NOT NULL REFERENCES core.models (id),
    old_guid        uuid NOT NULL,                                -- the entity merged away
    old_display_id  text NOT NULL DEFAULT '',
    old_name        text NOT NULL DEFAULT '',
    survivor_guid   uuid NOT NULL,                                -- the one kept
    merged_by       text NOT NULL,
    merged_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (model_id, old_guid)
);
CREATE INDEX entity_aliases_display_idx ON core.entity_aliases (model_id, lower(old_display_id));
COMMENT ON TABLE core.entity_aliases IS 'Entities merged away by dedupe (D361): their old guid and display ID still find the one kept';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.merge_requests TO eax_migrator;
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.entity_aliases TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
END;
$$;
