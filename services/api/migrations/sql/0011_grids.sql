-- =====================================================================================
-- 0011_grids: build phase 7 (version 0.7.0), grids, search and saved views
--   * saved views: a grid's or list's columns, filters and sort, kept by a person, optionally shared with
--     everyone who can read the model
--   * favourites: entities, models and saved views a person marks to find again
--   * search across attribute values and tags (trigram index on values)
-- The API decides who sees which rows (owner, or shared and the model readable).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.7.0', '0011_grids', 'Phase 7: grids for content and metamodel, search, saved views and favourites');

CREATE TABLE core.saved_views (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    owner       text NOT NULL,
    model_id    bigint REFERENCES core.models (id),
    view_kind   text NOT NULL,              -- entity_grid, relationship_grid, metamodel_grid, search
    target      text NOT NULL DEFAULT '',   -- the entity type guid, metamodel grid kind or relationship type
    name        text NOT NULL CHECK (length(btrim(name)) > 0),
    config      jsonb NOT NULL DEFAULT '{}',
    shared      boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX saved_views_lookup_idx ON core.saved_views (model_id, view_kind, target);
COMMENT ON TABLE core.saved_views IS 'Saved grid and list views (phase 7, REP-016): columns, filters, sort; private or shared';

CREATE TABLE core.favourites (
    username   text NOT NULL,
    kind       text NOT NULL CHECK (kind IN ('entity', 'model', 'view')),
    target     uuid NOT NULL,
    model_id   bigint REFERENCES core.models (id),
    label      text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (username, kind, target)
);
COMMENT ON TABLE core.favourites IS 'What a person marked to find again (phase 7, UI-016)';

CREATE INDEX attribute_values_text_trgm_idx ON core.attribute_values USING gin (value_text gin_trgm_ops) WHERE NOT is_deleted;
CREATE INDEX entities_name_trgm_idx ON core.entities USING gin (name gin_trgm_ops) WHERE NOT is_deleted;
