-- =====================================================================================
-- 0054_derived_types: an entity type derived from another (R2.9, D629; owner, 11 and 12 Nov 2026)
--   A design-time decision in the metamodel (ArchiMate's Specialization between the two types): the derived type gets
--   the base type's attributes and allowed relationships, plus its own. The application copies them onto the derived
--   type when a metamodel change is applied (eax/derived_types.py); each entity keeps all its own values. Columns,
--   foreign keys and indexes only (D248); no version change.
-- =====================================================================================

ALTER TABLE core.entity_types ADD COLUMN IF NOT EXISTS base_type_id integer
    REFERENCES core.entity_types (id) ON DELETE SET NULL;
ALTER TABLE core.entity_types DROP CONSTRAINT IF EXISTS entity_types_not_own_base;
ALTER TABLE core.entity_types ADD CONSTRAINT entity_types_not_own_base CHECK (base_type_id IS NULL OR base_type_id <> id);
CREATE INDEX IF NOT EXISTS entity_types_base ON core.entity_types (base_type_id) WHERE base_type_id IS NOT NULL;
COMMENT ON COLUMN core.entity_types.base_type_id IS 'R2.9: the type this one is derived from (ArchiMate Specialization), same metamodel';

ALTER TABLE core.item_attributes ADD COLUMN IF NOT EXISTS inherited_from integer
    REFERENCES core.item_attributes (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS item_attributes_inherited ON core.item_attributes (inherited_from) WHERE inherited_from IS NOT NULL;
COMMENT ON COLUMN core.item_attributes.inherited_from IS 'R2.9: the base type''s attribute this one was copied from';

ALTER TABLE core.allowed_relationships ADD COLUMN IF NOT EXISTS inherited_from integer
    REFERENCES core.allowed_relationships (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS allowed_relationships_inherited ON core.allowed_relationships (inherited_from) WHERE inherited_from IS NOT NULL;
COMMENT ON COLUMN core.allowed_relationships.inherited_from IS 'R2.9: the base type''s allowed relationship this one was copied from';
