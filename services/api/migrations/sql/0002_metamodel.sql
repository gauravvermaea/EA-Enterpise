-- =====================================================================================
-- EA Explorer phase 1: metamodel and generic repository content
-- This file is the source of the schema: Alembic (migrations/versions/0002_metamodel.py) runs it
-- when the api container starts. Edit it here; tests/sql/phase1_checks.sql checks it.
--
-- Design (see docs/database.md):
--   * Every row has a bigint key (id) used by all joins and foreign keys, and a guid: a global,
--     never-reused id used by the API, exchange files, deep copy and merge back. origin_guid
--     is the guid of the row it was copied from.
--   * Every row has the same housekeeping columns: workflow status (item_status), soft delete,
--     created/modified by and when, and a row_version kept by trigger.
--   * Every change is written to history.row_versions by trigger (old and new versions as JSON).
--   * A model owns its metamodel (layers, entity types, attribute types, relationship types,
--     pick lists, rules) and its content (entities, relationships, attribute values).
--     A template model has a metamodel only; a reference model is read-only; a project model is
--     a working model. Models form a hierarchy of any depth: parent_model_id is the model a model
--     merges back into (a work copy is simply a model with a parent, and can have work copies of
--     its own); source_model_id is the model it was created or copied from (lineage only).
--   * Content is generic: one entity table, one relationship table, one attribute value table
--     with a typed column per storage kind. New types and attributes are rows, never DDL.
-- =====================================================================================

-- ---------------------------------------------------------------- who is acting
-- The API sets eax.actor per transaction (SET LOCAL / set_config); otherwise the login name.
CREATE FUNCTION core.current_actor() RETURNS text LANGUAGE sql STABLE AS $$
    SELECT coalesce(nullif(current_setting('eax.actor', true), ''), session_user::text)
$$;

-- ---------------------------------------------------------------- reference lists (fixed)
CREATE TABLE core.item_statuses (
    code        text PRIMARY KEY,
    name        text NOT NULL,
    description text NOT NULL,
    sort_order  integer NOT NULL
);
INSERT INTO core.item_statuses VALUES
    ('created',      'Created',      'New, not yet submitted for review', 1),
    ('under_review', 'Under review', 'Submitted and waiting for a reviewer', 2),
    ('published',    'Published',    'Approved and visible to everyone who may read the model', 3),
    ('retired',      'Retired',      'No longer in use; kept for history', 4);

CREATE TABLE core.model_kinds (
    code        text PRIMARY KEY,
    name        text NOT NULL,
    description text NOT NULL,
    holds_content boolean NOT NULL,
    read_only   boolean NOT NULL
);
INSERT INTO core.model_kinds VALUES
    ('template',  'Template',        'A metamodel with no content; new models start from it', false, true),
    ('reference', 'Reference model', 'Read-only content (industry and high-level models)',     true,  true),
    ('project',   'Project model',   'A working model; copies of it (any depth) merge back to their parent', true, false);

CREATE TABLE core.data_types (
    code        text PRIMARY KEY,
    name        text NOT NULL,
    storage     text NOT NULL CHECK (storage IN ('text', 'number', 'date', 'boolean', 'ref')),
    sql_type    text NOT NULL,   -- column type used by get_entity and the report views
    sort_order  integer NOT NULL
);
INSERT INTO core.data_types VALUES
    ('text',       'Text',             'text',    'text',    1),
    ('long_text',  'Long text',        'text',    'text',    2),
    ('integer',    'Whole number',     'number',  'bigint',  3),
    ('decimal',    'Decimal number',   'number',  'numeric', 4),
    ('currency',   'Currency amount',  'number',  'numeric', 5),
    ('percent',    'Percentage',       'number',  'numeric', 6),
    ('date',       'Date',             'date',    'date',    7),
    ('boolean',    'Yes / no',         'boolean', 'boolean', 8),
    ('list',       'Pick list',        'text',    'text',    9),
    ('url',        'Web address',      'text',    'text',    10),
    ('email',      'Email address',    'text',    'text',    11),
    ('entity_ref', 'Link to an entity','ref',     'bigint',  12);

CREATE TABLE core.rule_types (
    code        text PRIMARY KEY,
    name        text NOT NULL,
    description text NOT NULL
);
INSERT INTO core.rule_types VALUES
    ('mandatory',   'Mandatory',      'A value is required'),
    ('list',        'Pick list',      'The value must come from param1 (a pick list code)'),
    ('min_value',   'Minimum',        'Number at least param1'),
    ('max_value',   'Maximum',        'Number at most param1'),
    ('range',       'Range',          'Number from param1 to param2'),
    ('min_length',  'Minimum length', 'Text at least param1 characters'),
    ('max_length',  'Maximum length', 'Text at most param1 characters'),
    ('regex',       'Pattern',        'Text matches the regular expression in param1'),
    ('date_range',  'Date range',     'Date from param1 to param2'),
    ('date_order',  'Date order',     'Date after the attribute named in param1'),
    ('unique',      'Unique',         'No other entity of the same type has this value'),
    ('entity_ref',  'Entity link',    'The value links to an entity of the type in param1'),
    ('required_if', 'Required if',    'Required when attribute param1 has value param2');

-- ---------------------------------------------------------------- housekeeping triggers
-- Keeps created_* fixed, sets modified_* and counts row_version.
CREATE FUNCTION core.stamp_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.row_version := 1;
    ELSE
        NEW.created_at  := OLD.created_at;
        NEW.created_by  := OLD.created_by;
        NEW.row_version := OLD.row_version + 1;
        NEW.modified_at := now();
        NEW.modified_by := core.current_actor();
    END IF;
    RETURN NEW;
END;
$$;

-- One history table for every repository table: each version of each row as JSON.
-- A label (for example a baseline or import name) is taken from the setting eax.history_label
-- when the change is made.
CREATE TABLE history.row_versions (
    id          bigserial PRIMARY KEY,
    table_name  text        NOT NULL,
    row_id      bigint      NOT NULL,
    row_guid    uuid        NOT NULL,
    model_id    bigint,
    row_version integer     NOT NULL,
    operation   text        NOT NULL CHECK (operation IN ('insert', 'update', 'delete')),
    data        jsonb       NOT NULL,
    label       text,
    changed_at  timestamptz NOT NULL DEFAULT now(),
    changed_by  text        NOT NULL DEFAULT core.current_actor()
);
CREATE INDEX row_versions_row_idx   ON history.row_versions (table_name, row_id, row_version);
CREATE INDEX row_versions_guid_idx  ON history.row_versions (row_guid);
CREATE INDEX row_versions_model_idx ON history.row_versions (model_id, changed_at);

CREATE FUNCTION history.capture() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    rec  jsonb;
BEGIN
    rec := to_jsonb(CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
    INSERT INTO history.row_versions (table_name, row_id, row_guid, model_id, row_version, operation, data, label)
    VALUES (TG_TABLE_NAME,
            (rec ->> 'id')::bigint,
            (rec ->> 'guid')::uuid,
            CASE WHEN TG_TABLE_NAME = 'models' THEN (rec ->> 'id')::bigint
                 ELSE (rec ->> 'model_id')::bigint END,
            coalesce((rec ->> 'row_version')::integer, 0),
            lower(TG_OP),
            rec,
            nullif(current_setting('eax.history_label', true), ''));
    RETURN NULL;
END;
$$;

-- Read access to a model. Phase 1: everyone signed in may read every model. Model roles
-- (build phase 4) replace this function; get_entity and the report views already call it.
CREATE FUNCTION core.can_read_model(p_model bigint) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT true
$$;
-- ---------------------------------------------------------------- models
CREATE TABLE core.models (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    name            text NOT NULL,
    description     text NOT NULL DEFAULT '',
    kind_code       text NOT NULL REFERENCES core.model_kinds (code),
    parent_model_id bigint REFERENCES core.models (id),  -- the model this one merges back into (NULL: top level)
    source_model_id bigint REFERENCES core.models (id),  -- the model it was created or copied from (lineage)
    metamodel_name  text NOT NULL DEFAULT '',         -- for example 'ArchiMate 4'
    metamodel_version integer NOT NULL DEFAULT 1,     -- counts metamodel publications
    is_locked       boolean NOT NULL DEFAULT false,  -- read-only (templates, reference models)
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX models_name_uq ON core.models (lower(name)) WHERE NOT is_deleted;

-- ---------------------------------------------------------------- metamodel (owned by a model)
CREATE TABLE core.layers (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id    bigint NOT NULL REFERENCES core.models (id),
    code        text NOT NULL,
    name        text NOT NULL,
    description text NOT NULL DEFAULT '',
    colour      text NOT NULL DEFAULT 'EEEEEE',   -- hex fill used for shapes and the browser
    sort_order  integer NOT NULL DEFAULT 0,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1,
    UNIQUE (model_id, code)
);
CREATE TABLE core.entity_types (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id    bigint NOT NULL REFERENCES core.models (id),
    layer_id    bigint NOT NULL REFERENCES core.layers (id),
    code        text NOT NULL,                    -- ApplicationComponent
    name        text NOT NULL,                    -- Application Component
    description text NOT NULL DEFAULT '',
    aspect      text NOT NULL DEFAULT '',         -- Internal Active Structure, Behaviour...
    id_prefix   text NOT NULL,                    -- APP: display IDs APP-0001
    table_name  text NOT NULL CHECK (table_name ~ '^[a-z][a-z0-9_]{0,50}$'),  -- application_component
    sort_order  integer NOT NULL DEFAULT 0,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1,
    UNIQUE (model_id, code),
    UNIQUE (model_id, table_name)
);
CREATE TABLE core.relationship_types (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id    bigint NOT NULL REFERENCES core.models (id),
    code        text NOT NULL,                    -- Serving
    name        text NOT NULL,                    -- Serving
    verb        text NOT NULL DEFAULT '',         -- serves (read source -> target)
    category    text NOT NULL DEFAULT '',         -- Structural, Dependency, Dynamic, Other
    is_directed boolean NOT NULL DEFAULT true,
    description text NOT NULL DEFAULT '',
    sort_order  integer NOT NULL DEFAULT 0,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1,
    UNIQUE (model_id, code)
);
CREATE TABLE core.pick_lists (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id    bigint NOT NULL REFERENCES core.models (id),
    code        text NOT NULL,
    name        text NOT NULL,
    description text NOT NULL DEFAULT '',
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1,
    UNIQUE (model_id, code)
);
CREATE TABLE core.pick_list_values (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id     bigint NOT NULL REFERENCES core.models (id),
    pick_list_id bigint NOT NULL REFERENCES core.pick_lists (id),
    value        text NOT NULL,
    description  text NOT NULL DEFAULT '',
    sort_order   integer NOT NULL DEFAULT 0,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1,
    UNIQUE (pick_list_id, value)
);
CREATE TABLE core.attribute_types (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id       bigint NOT NULL REFERENCES core.models (id),
    code           text NOT NULL,                 -- GoLiveDate
    name           text NOT NULL,                 -- Go-live date
    description    text NOT NULL DEFAULT '',
    data_type_code text NOT NULL REFERENCES core.data_types (code),
    pick_list_id   bigint REFERENCES core.pick_lists (id),
    unit           text NOT NULL DEFAULT '',      -- ZAR, days...
    column_name    text NOT NULL CHECK (column_name ~ '^[a-z][a-z0-9_]{0,50}$'),  -- go_live_date
    CHECK ((data_type_code = 'list') = (pick_list_id IS NOT NULL)),
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1,
    UNIQUE (model_id, code),
    UNIQUE (model_id, column_name)
);
CREATE TABLE core.item_attributes (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id             bigint NOT NULL REFERENCES core.models (id),
    attribute_type_id    bigint NOT NULL REFERENCES core.attribute_types (id),
    entity_type_id       bigint REFERENCES core.entity_types (id),
    relationship_type_id bigint REFERENCES core.relationship_types (id),
    is_required          boolean NOT NULL DEFAULT false,
    section              text NOT NULL DEFAULT 'General',  -- groups fields on forms
    sort_order           integer NOT NULL DEFAULT 0,
    CHECK (num_nonnulls(entity_type_id, relationship_type_id) = 1),
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX item_attributes_entity_uq ON core.item_attributes (entity_type_id, attribute_type_id)
    WHERE entity_type_id IS NOT NULL AND NOT is_deleted;
CREATE UNIQUE INDEX item_attributes_rel_uq ON core.item_attributes (relationship_type_id, attribute_type_id)
    WHERE relationship_type_id IS NOT NULL AND NOT is_deleted;
CREATE TABLE core.validation_rules (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id          bigint NOT NULL REFERENCES core.models (id),
    attribute_type_id bigint REFERENCES core.attribute_types (id),   -- the attribute checked, or
    field_name        text CHECK (field_name IN ('name', 'description', 'display_id')),  -- a built-in field
    entity_type_id    bigint REFERENCES core.entity_types (id),      -- empty: every type
    rule_type_code    text NOT NULL REFERENCES core.rule_types (code),
    param1            text NOT NULL DEFAULT '',
    param2            text NOT NULL DEFAULT '',
    severity          text NOT NULL DEFAULT 'error' CHECK (severity IN ('error', 'warning')),
    message           text NOT NULL,
    sort_order        integer NOT NULL DEFAULT 0,
    CHECK (num_nonnulls(attribute_type_id, field_name) = 1),
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1
);
CREATE TABLE core.allowed_relationships (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id             bigint NOT NULL REFERENCES core.models (id),
    relationship_type_id bigint NOT NULL REFERENCES core.relationship_types (id),
    source_type_id       bigint NOT NULL REFERENCES core.entity_types (id),
    target_type_id       bigint NOT NULL REFERENCES core.entity_types (id),
    note                 text NOT NULL DEFAULT '',
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1,
    UNIQUE (relationship_type_id, source_type_id, target_type_id)
);

-- ---------------------------------------------------------------- content (generic)
CREATE TABLE core.entities (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id         bigint NOT NULL REFERENCES core.models (id),
    entity_type_id   bigint NOT NULL REFERENCES core.entity_types (id),
    display_id       text NOT NULL DEFAULT '',     -- APP-0012; filled by trigger when empty
    name             text NOT NULL CHECK (length(trim(name)) > 0),
    description      text NOT NULL DEFAULT '',
    parent_entity_id bigint REFERENCES core.entities (id),  -- hierarchy: capability levels, sub-processes
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX entities_display_id_uq ON core.entities (model_id, display_id) WHERE NOT is_deleted;
CREATE TABLE core.relationships (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id             bigint NOT NULL REFERENCES core.models (id),
    relationship_type_id bigint NOT NULL REFERENCES core.relationship_types (id),
    source_entity_id     bigint NOT NULL REFERENCES core.entities (id),
    target_entity_id     bigint NOT NULL REFERENCES core.entities (id),
    name                 text NOT NULL DEFAULT '',     -- optional label shown on the connector
    description          text NOT NULL DEFAULT '',
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1
);
CREATE TABLE core.attribute_values (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id          bigint NOT NULL REFERENCES core.models (id),
    attribute_type_id bigint NOT NULL REFERENCES core.attribute_types (id),
    entity_id         bigint REFERENCES core.entities (id),        -- the owner: an entity or
    relationship_id   bigint REFERENCES core.relationships (id),  -- a relationship
    value_text        text,
    value_number      numeric,
    value_date        date,
    value_bool        boolean,
    value_ref         bigint REFERENCES core.entities (id),
    CHECK (num_nonnulls(entity_id, relationship_id) = 1),
    CHECK (num_nonnulls(value_text, value_number, value_date, value_bool, value_ref) <= 1),
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX attribute_values_entity_uq ON core.attribute_values (entity_id, attribute_type_id)
    WHERE entity_id IS NOT NULL AND NOT is_deleted;
CREATE UNIQUE INDEX attribute_values_rel_uq ON core.attribute_values (relationship_id, attribute_type_id)
    WHERE relationship_id IS NOT NULL AND NOT is_deleted;
CREATE TABLE core.display_id_counters (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- internal key for joins
    model_id       bigint NOT NULL REFERENCES core.models (id),
    entity_type_id bigint NOT NULL REFERENCES core.entity_types (id),
    last_number    integer NOT NULL DEFAULT 0,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- global id: API, exchange, copy and merge
    origin_guid  uuid,                                   -- guid of the row this was copied from
    status_code  text NOT NULL DEFAULT 'published' REFERENCES core.item_statuses (code),
    is_deleted   boolean NOT NULL DEFAULT false,         -- soft delete; history keeps every version
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    modified_by  text NOT NULL DEFAULT core.current_actor(),
    row_version  integer NOT NULL DEFAULT 1,
    UNIQUE (model_id, entity_type_id)
);

-- ---------------------------------------------------------------- indexes
CREATE INDEX models_parent_model_id_idx ON core.models (parent_model_id);
CREATE INDEX models_source_model_id_idx ON core.models (source_model_id);
CREATE INDEX models_origin_guid_idx ON core.models (origin_guid);
CREATE INDEX layers_model_id_idx ON core.layers (model_id);
CREATE INDEX entity_types_model_id_idx ON core.entity_types (model_id);
CREATE INDEX entity_types_layer_id_idx ON core.entity_types (layer_id);
CREATE INDEX entity_types_origin_guid_idx ON core.entity_types (origin_guid);
CREATE INDEX relationship_types_model_id_idx ON core.relationship_types (model_id);
CREATE INDEX relationship_types_origin_guid_idx ON core.relationship_types (origin_guid);
CREATE INDEX pick_lists_model_id_idx ON core.pick_lists (model_id);
CREATE INDEX pick_list_values_pick_list_id_idx ON core.pick_list_values (pick_list_id);
CREATE INDEX attribute_types_model_id_idx ON core.attribute_types (model_id);
CREATE INDEX attribute_types_pick_list_id_idx ON core.attribute_types (pick_list_id);
CREATE INDEX attribute_types_origin_guid_idx ON core.attribute_types (origin_guid);
CREATE INDEX item_attributes_attribute_type_id_idx ON core.item_attributes (attribute_type_id);
CREATE INDEX validation_rules_model_id_idx ON core.validation_rules (model_id);
CREATE INDEX validation_rules_attribute_type_id_idx ON core.validation_rules (attribute_type_id);
CREATE INDEX allowed_relationships_model_id_idx ON core.allowed_relationships (model_id);
CREATE INDEX allowed_relationships_source_type_id_idx ON core.allowed_relationships (source_type_id);
CREATE INDEX allowed_relationships_target_type_id_idx ON core.allowed_relationships (target_type_id);
CREATE INDEX entities_model_id_entity_type_id_idx ON core.entities (model_id, entity_type_id);
CREATE INDEX entities_parent_entity_id_idx ON core.entities (parent_entity_id);
CREATE INDEX entities_origin_guid_idx ON core.entities (origin_guid);
CREATE INDEX entities_model_id_name_idx ON core.entities (model_id, lower(name));
CREATE INDEX relationships_model_id_relationship_type_id_idx ON core.relationships (model_id, relationship_type_id);
CREATE INDEX relationships_source_entity_id_idx ON core.relationships (source_entity_id);
CREATE INDEX relationships_target_entity_id_idx ON core.relationships (target_entity_id);
CREATE INDEX relationships_origin_guid_idx ON core.relationships (origin_guid);
CREATE INDEX attribute_values_attribute_type_id_idx ON core.attribute_values (attribute_type_id);
CREATE INDEX attribute_values_value_ref_idx ON core.attribute_values (value_ref);
CREATE INDEX attribute_values_origin_guid_idx ON core.attribute_values (origin_guid);

-- ---------------------------------------------------------------- integrity rules (triggers)
-- Rows must belong to the same model as what they point at; content cannot be added to a
-- template; relationships must be allowed by the metamodel; attribute values must fit the
-- attribute's data type and the owner's type.

-- The model hierarchy: a parent is a working model (it can take the merge), and a model can never
-- be its own ancestor. Any depth is allowed.
CREATE FUNCTION core.check_model() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_parent core.models%ROWTYPE;
    v_kind   core.model_kinds%ROWTYPE;
BEGIN
    IF NEW.parent_model_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF NEW.parent_model_id = NEW.id THEN
        RAISE EXCEPTION 'A model cannot be its own parent';
    END IF;
    SELECT * INTO v_parent FROM core.models WHERE id = NEW.parent_model_id;
    SELECT * INTO v_kind FROM core.model_kinds WHERE code = v_parent.kind_code;
    IF NOT v_kind.holds_content OR v_kind.read_only OR v_parent.is_locked THEN
        RAISE EXCEPTION 'Model "%" cannot be a parent: it is a % and changes cannot merge into it',
            v_parent.name, lower(v_kind.name)
            USING HINT = 'Templates and reference models can be the source of a model (source_model_id), not its parent.';
    END IF;
    IF TG_OP = 'UPDATE' AND EXISTS (
        WITH RECURSIVE up AS (
            SELECT id, parent_model_id FROM core.models WHERE id = NEW.parent_model_id
            UNION ALL
            SELECT m.id, m.parent_model_id FROM core.models m JOIN up ON m.id = up.parent_model_id
        ) SELECT 1 FROM up WHERE id = NEW.id) THEN
        RAISE EXCEPTION 'Model "%" cannot be under "%": that would make a loop', NEW.name, v_parent.name;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION core.check_entity() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_kind   text;
    v_type   core.entity_types%ROWTYPE;
    v_number integer;
BEGIN
    SELECT k.code INTO v_kind FROM core.models m JOIN core.model_kinds k ON k.code = m.kind_code
     WHERE m.id = NEW.model_id;
    IF v_kind = 'template' THEN
        RAISE EXCEPTION 'A template model holds a metamodel only: entities cannot be added';
    END IF;
    SELECT * INTO v_type FROM core.entity_types WHERE id = NEW.entity_type_id;
    IF v_type.model_id <> NEW.model_id THEN
        RAISE EXCEPTION 'Entity type % belongs to another model', v_type.code;
    END IF;
    IF NEW.parent_entity_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core.entities p WHERE p.id = NEW.parent_entity_id AND p.model_id = NEW.model_id) THEN
        RAISE EXCEPTION 'The parent entity must be in the same model';
    END IF;
    IF NEW.parent_entity_id = NEW.id THEN
        RAISE EXCEPTION 'An entity cannot be its own parent';
    END IF;
    IF coalesce(NEW.display_id, '') = '' THEN
        INSERT INTO core.display_id_counters (model_id, entity_type_id, last_number)
        VALUES (NEW.model_id, NEW.entity_type_id, 1)
        ON CONFLICT (model_id, entity_type_id)
            DO UPDATE SET last_number = core.display_id_counters.last_number + 1
        RETURNING last_number INTO v_number;
        NEW.display_id := v_type.id_prefix || '-' || lpad(v_number::text, 4, '0');
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION core.check_relationship() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_src core.entities%ROWTYPE;
    v_tgt core.entities%ROWTYPE;
    v_rel core.relationship_types%ROWTYPE;
BEGIN
    SELECT * INTO v_src FROM core.entities WHERE id = NEW.source_entity_id;
    SELECT * INTO v_tgt FROM core.entities WHERE id = NEW.target_entity_id;
    SELECT * INTO v_rel FROM core.relationship_types WHERE id = NEW.relationship_type_id;
    IF v_src.model_id <> NEW.model_id OR v_tgt.model_id <> NEW.model_id OR v_rel.model_id <> NEW.model_id THEN
        RAISE EXCEPTION 'A relationship and both its ends must be in the same model';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM core.allowed_relationships a
         WHERE a.relationship_type_id = NEW.relationship_type_id
           AND a.source_type_id = v_src.entity_type_id
           AND a.target_type_id = v_tgt.entity_type_id
           AND NOT a.is_deleted) THEN
        RAISE EXCEPTION 'The metamodel does not allow % from % to %',
            v_rel.name,
            (SELECT name FROM core.entity_types WHERE id = v_src.entity_type_id),
            (SELECT name FROM core.entity_types WHERE id = v_tgt.entity_type_id);
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION core.check_attribute_value() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_attr    core.attribute_types%ROWTYPE;
    v_storage text;
    v_owner_model bigint;
    v_owner_type  bigint;
BEGIN
    SELECT * INTO v_attr FROM core.attribute_types WHERE id = NEW.attribute_type_id;
    SELECT storage INTO v_storage FROM core.data_types WHERE code = v_attr.data_type_code;
    IF v_attr.model_id <> NEW.model_id THEN
        RAISE EXCEPTION 'Attribute % belongs to another model', v_attr.code;
    END IF;
    -- the attribute must be mapped to the owner's type
    IF NEW.entity_id IS NOT NULL THEN
        SELECT model_id, entity_type_id INTO v_owner_model, v_owner_type FROM core.entities WHERE id = NEW.entity_id;
        IF NOT EXISTS (SELECT 1 FROM core.item_attributes WHERE entity_type_id = v_owner_type
                         AND attribute_type_id = NEW.attribute_type_id AND NOT is_deleted) THEN
            RAISE EXCEPTION 'Attribute % does not apply to this entity''s type', v_attr.name;
        END IF;
    ELSE
        SELECT model_id, relationship_type_id INTO v_owner_model, v_owner_type FROM core.relationships WHERE id = NEW.relationship_id;
        IF NOT EXISTS (SELECT 1 FROM core.item_attributes WHERE relationship_type_id = v_owner_type
                         AND attribute_type_id = NEW.attribute_type_id AND NOT is_deleted) THEN
            RAISE EXCEPTION 'Attribute % does not apply to this relationship''s type', v_attr.name;
        END IF;
    END IF;
    IF v_owner_model <> NEW.model_id THEN
        RAISE EXCEPTION 'An attribute value must be in the same model as its owner';
    END IF;
    -- the value must sit in the column for the attribute's data type
    IF (v_storage <> 'text'    AND NEW.value_text   IS NOT NULL)
    OR (v_storage <> 'number'  AND NEW.value_number IS NOT NULL)
    OR (v_storage <> 'date'    AND NEW.value_date   IS NOT NULL)
    OR (v_storage <> 'boolean' AND NEW.value_bool   IS NOT NULL)
    OR (v_storage <> 'ref'     AND NEW.value_ref    IS NOT NULL) THEN
        RAISE EXCEPTION 'Attribute % holds % values', v_attr.name, v_attr.data_type_code;
    END IF;
    IF v_attr.data_type_code = 'integer' AND NEW.value_number <> trunc(NEW.value_number) THEN
        RAISE EXCEPTION 'Attribute % holds whole numbers', v_attr.name;
    END IF;
    IF v_attr.pick_list_id IS NOT NULL AND NEW.value_text IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core.pick_list_values WHERE pick_list_id = v_attr.pick_list_id
           AND value = NEW.value_text AND NOT is_deleted) THEN
        RAISE EXCEPTION '"%" is not in the pick list for %', NEW.value_text, v_attr.name;
    END IF;
    IF NEW.value_ref IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core.entities WHERE id = NEW.value_ref AND model_id = NEW.model_id) THEN
        RAISE EXCEPTION 'Attribute % must link to an entity in the same model', v_attr.name;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER models_check BEFORE INSERT OR UPDATE OF parent_model_id ON core.models
    FOR EACH ROW EXECUTE FUNCTION core.check_model();
CREATE TRIGGER entities_check BEFORE INSERT OR UPDATE ON core.entities
    FOR EACH ROW EXECUTE FUNCTION core.check_entity();
CREATE TRIGGER relationships_check BEFORE INSERT OR UPDATE ON core.relationships
    FOR EACH ROW EXECUTE FUNCTION core.check_relationship();
CREATE TRIGGER attribute_values_check BEFORE INSERT OR UPDATE ON core.attribute_values
    FOR EACH ROW EXECUTE FUNCTION core.check_attribute_value();

-- ---------------------------------------------------------------- housekeeping and history on every table
CREATE TRIGGER models_stamp BEFORE INSERT OR UPDATE ON core.models FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER models_history AFTER INSERT OR UPDATE OR DELETE ON core.models FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER layers_stamp BEFORE INSERT OR UPDATE ON core.layers FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER layers_history AFTER INSERT OR UPDATE OR DELETE ON core.layers FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER entity_types_stamp BEFORE INSERT OR UPDATE ON core.entity_types FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER entity_types_history AFTER INSERT OR UPDATE OR DELETE ON core.entity_types FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER relationship_types_stamp BEFORE INSERT OR UPDATE ON core.relationship_types FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER relationship_types_history AFTER INSERT OR UPDATE OR DELETE ON core.relationship_types FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER pick_lists_stamp BEFORE INSERT OR UPDATE ON core.pick_lists FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER pick_lists_history AFTER INSERT OR UPDATE OR DELETE ON core.pick_lists FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER pick_list_values_stamp BEFORE INSERT OR UPDATE ON core.pick_list_values FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER pick_list_values_history AFTER INSERT OR UPDATE OR DELETE ON core.pick_list_values FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER attribute_types_stamp BEFORE INSERT OR UPDATE ON core.attribute_types FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER attribute_types_history AFTER INSERT OR UPDATE OR DELETE ON core.attribute_types FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER item_attributes_stamp BEFORE INSERT OR UPDATE ON core.item_attributes FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER item_attributes_history AFTER INSERT OR UPDATE OR DELETE ON core.item_attributes FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER validation_rules_stamp BEFORE INSERT OR UPDATE ON core.validation_rules FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER validation_rules_history AFTER INSERT OR UPDATE OR DELETE ON core.validation_rules FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER allowed_relationships_stamp BEFORE INSERT OR UPDATE ON core.allowed_relationships FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER allowed_relationships_history AFTER INSERT OR UPDATE OR DELETE ON core.allowed_relationships FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER entities_stamp BEFORE INSERT OR UPDATE ON core.entities FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER entities_history AFTER INSERT OR UPDATE OR DELETE ON core.entities FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER relationships_stamp BEFORE INSERT OR UPDATE ON core.relationships FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER relationships_history AFTER INSERT OR UPDATE OR DELETE ON core.relationships FOR EACH ROW EXECUTE FUNCTION history.capture();
CREATE TRIGGER attribute_values_stamp BEFORE INSERT OR UPDATE ON core.attribute_values FOR EACH ROW EXECUTE FUNCTION core.stamp_row();
CREATE TRIGGER attribute_values_history AFTER INSERT OR UPDATE OR DELETE ON core.attribute_values FOR EACH ROW EXECUTE FUNCTION history.capture();

-- History is append-only, like the audit log
CREATE FUNCTION history.refuse_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING MESSAGE = 'history.row_versions is append-only: ' || TG_OP || ' refused';
END;
$$;
CREATE TRIGGER row_versions_no_change BEFORE UPDATE OR DELETE ON history.row_versions
    FOR EACH ROW EXECUTE FUNCTION history.refuse_change();
