-- =====================================================================================
-- 0033_drawn_views: version 0.16.0, drawn views in draw.io (phases 28 and 29; owner, 9 and 10 Nov 2026, D354, D386 to D402)
--   * every entity type gets a look: its ArchiMate notation (the shape and icon) and, if wanted, its own fill colour
--     (else its domain's); a junction type is a connector (D397)
--   * drawn views themselves (the draw.io files and their versions) and a model's own view definitions are kept by the
--     views service in its own database (eaxviews, D405): nothing of them here
--   * an entity's own icon (SVG or PNG, small)
--   * a drawn view as a project's evidence: for a deliverable (an item) or a key question, a link only (D408)
-- Rows only: the rules are in eax/drawn_views.py, eax/notation.py and eax/junctions.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.16.0', '0033_drawn_views', 'Drawn views in draw.io; entity type notation; entity icons; junctions');

ALTER TABLE core.entity_types
    ADD COLUMN notation     text NOT NULL DEFAULT '',        -- the ArchiMate element whose shape and icon it shows (eax.notation)
    ADD COLUMN fill_colour  text NOT NULL DEFAULT '',        -- its own fill colour (RRGGBB); empty: the domain's
    ADD COLUMN is_connector boolean NOT NULL DEFAULT false;  -- a junction (D397, D402): a connector, not an element

CREATE TABLE core.entity_icons (
    entity_id    bigint PRIMARY KEY REFERENCES core.entities (id) ON DELETE CASCADE,
    content_type text NOT NULL CHECK (content_type IN ('image/svg+xml', 'image/png')),
    content      bytea NOT NULL,
    uploaded_by  text NOT NULL,
    uploaded_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE proj.view_evidence (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    item_id     bigint REFERENCES proj.items (id) ON DELETE CASCADE,          -- a deliverable's artifact
    question_id bigint REFERENCES proj.key_questions (id) ON DELETE CASCADE,  -- or a key question's answer
    model_guid  uuid NOT NULL,                                                -- the model and its drawn view, by guid: nothing
    view_guid   uuid NOT NULL,                                                --   crosses from proj to core (D266); the view is the views service's (D405)
    version_no  integer,                                                      -- one version (read only); empty: the live view
    note        text NOT NULL DEFAULT '',
    added_by    text NOT NULL,
    added_at    timestamptz NOT NULL DEFAULT now(),
    CHECK ((item_id IS NULL) <> (question_id IS NULL))
);
CREATE INDEX view_evidence_project ON proj.view_evidence (project_id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.entity_icons TO eax_migrator;
        GRANT SELECT, INSERT, UPDATE, DELETE ON proj.view_evidence TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;

-- a Web address attribute becomes a Link: one or more links, each with a note (owner, 10 Nov 2026, D418); same code
UPDATE core.data_types SET name = 'Link' WHERE code = 'url';
