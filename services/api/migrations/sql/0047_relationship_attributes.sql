-- =====================================================================================
-- 0047_relationship_attributes: version 0.19.0, attributes on relationships per allowed relationship (D563, D564)
--   A relationship type's attribute (core.item_attributes with relationship_type_id) applies to every allowed
--   relationship (mapping) of that type, unless it is limited to some of them here: then it applies only to those
--   mappings (source type + relationship type + target type), each with its own "required". For example Port on
--   Node - Association - Node, and nothing on Equipment - Association - Work Package.
-- Rows only: which attributes a relationship has is worked out in eax/content.py (no logic in the database, D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.19.0', '0047_relationship_attributes', 'Relationship attributes limited to allowed relationships')
ON CONFLICT (version) DO NOTHING;   -- several 0.19.0 migrations: the first one writes the version

CREATE TABLE core.item_attribute_mappings (
    id                      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id                bigint NOT NULL REFERENCES core.models (id),
    item_attribute_id       bigint NOT NULL REFERENCES core.item_attributes (id),
    allowed_relationship_id bigint NOT NULL REFERENCES core.allowed_relationships (id),
    is_required             boolean NOT NULL DEFAULT false,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    is_deleted   boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL DEFAULT core.current_actor()
);
CREATE UNIQUE INDEX item_attribute_mappings_uq ON core.item_attribute_mappings (item_attribute_id, allowed_relationship_id)
    WHERE NOT is_deleted;
CREATE INDEX item_attribute_mappings_allowed ON core.item_attribute_mappings (allowed_relationship_id) WHERE NOT is_deleted;
CREATE INDEX item_attribute_mappings_model ON core.item_attribute_mappings (model_id);
COMMENT ON TABLE core.item_attribute_mappings IS
    'A relationship type''s attribute limited to some allowed relationships (mappings), each with its own required flag (D564)';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.item_attribute_mappings TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
END;
$$;
