-- =====================================================================================
-- 0001_views: the views service's own database (phases 28 and 29; owner, 10 Nov 2026, D405 to D407)
--   * a model's drawn views: draw.io files, each save a version (the last save wins, after a warning)
--   * which versions a model's tags hold (never dropped, whatever EAX_VIEWS_KEEP_VERSIONS says)
--   * a model's own generated-view definitions (copies of the organisation's standard views, changed for the model);
--     the pictures of generated views are never stored: they are drawn from the model each time
-- Models, entities and relationships are in EA Explorer's main database: kept here by guid only (no foreign key across
-- databases). Rows only: the rules are in viewsvc (D248).
-- =====================================================================================

CREATE SCHEMA IF NOT EXISTS views;

CREATE TABLE views.schema_versions (
    version     text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE views.drawn_views (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    model_guid  uuid NOT NULL,                               -- the model in EA Explorer
    name        text NOT NULL,
    description text NOT NULL DEFAULT '',
    source      text NOT NULL DEFAULT 'new'
                CHECK (source IN ('new', 'copy', 'generated', 'mcp', 'model-copy', 'merge', 'package')),
    source_note text NOT NULL DEFAULT '',                    -- copied from which view, or which generated picture
    is_deleted  boolean NOT NULL DEFAULT false,
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_by text NOT NULL,
    modified_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX drawn_views_model ON views.drawn_views (model_guid) WHERE NOT is_deleted;
CREATE UNIQUE INDEX drawn_views_name ON views.drawn_views (model_guid, lower(name)) WHERE NOT is_deleted;

CREATE TABLE views.drawn_view_versions (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    view_id      bigint NOT NULL REFERENCES views.drawn_views (id) ON DELETE CASCADE,
    version_no   integer NOT NULL,
    xml          text NOT NULL,                              -- the draw.io file, uncompressed
    note         text NOT NULL DEFAULT '',
    model_marker timestamptz,                                -- the model's last content change when it was saved
    saved_by     text NOT NULL,
    saved_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (view_id, version_no)
);

-- the versions a model's tag keeps (D354: a tag keeps the views as they were)
CREATE TABLE views.tag_holds (
    tag_guid    uuid NOT NULL,
    model_guid  uuid NOT NULL,
    view_id     bigint NOT NULL REFERENCES views.drawn_views (id) ON DELETE CASCADE,
    version_no  integer NOT NULL,
    held_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tag_guid, view_id)
);
CREATE INDEX tag_holds_view ON views.tag_holds (view_id, version_no);

-- a model's own generated views (D406): a definition, drawn from the model each time it is opened
CREATE TABLE views.model_views (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid               uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    model_guid         uuid NOT NULL,
    name               text NOT NULL,
    category           text NOT NULL DEFAULT 'Model',
    purpose            text NOT NULL DEFAULT '',
    concerns           text NOT NULL DEFAULT '',
    stakeholders       text NOT NULL DEFAULT '',
    element_types      text[] NOT NULL DEFAULT '{}',
    relationship_types text[] NOT NULL DEFAULT '{}',          -- empty: every type
    heat_attribute     text NOT NULL DEFAULT 'Lifecycle',
    copied_from        text NOT NULL DEFAULT '',              -- the standard view's code, or another of the model's own
    is_deleted         boolean NOT NULL DEFAULT false,
    created_by         text NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    modified_by        text NOT NULL,
    modified_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX model_views_model ON views.model_views (model_guid) WHERE NOT is_deleted;
CREATE UNIQUE INDEX model_views_name ON views.model_views (model_guid, lower(name)) WHERE NOT is_deleted;

INSERT INTO views.schema_versions (version) VALUES ('0001_views');
