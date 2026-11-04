-- =====================================================================================
-- 0010_data_entry: build phase 6 (version 0.6.0), data entry in forms
--   * tags on entities (REP-026)
--   * a value saved although it fails a validation rule keeps the rule's details (D48: rules warn, never block)
--   * a relationship outside the metamodel can be added from data entry: it adds the allowed mapping to
--     the model's metamodel, flagged as added from content (D49)
--   * tags for reports (rpt.entity_tags)
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.6.0', '0010_data_entry', 'Phase 6: data entry in forms, tags, rule overrides, relationships outside the metamodel');

-- ---------------------------------------------------------------- tags
ALTER TABLE core.entities ADD COLUMN tags text[] NOT NULL DEFAULT '{}';
CREATE INDEX entities_tags_idx ON core.entities USING gin (tags);
COMMENT ON COLUMN core.entities.tags IS 'Free tags (REP-026), lower case, no duplicates';

CREATE FUNCTION core.clean_tags() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.tags := coalesce((SELECT array_agg(DISTINCT t ORDER BY t)
                            FROM (SELECT lower(btrim(x)) AS t FROM unnest(NEW.tags) AS x) s
                           WHERE t <> ''), '{}');
    RETURN NEW;
END;
$$;
CREATE TRIGGER entities_3_tags BEFORE INSERT OR UPDATE OF tags ON core.entities
    FOR EACH ROW EXECUTE FUNCTION core.clean_tags();

-- a copied entity keeps its tags (core.copy_model lists the columns it copies; tags came later)
CREATE FUNCTION core.copy_tags() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.origin_guid IS NOT NULL AND cardinality(NEW.tags) = 0 AND core.copying_into(NEW.model_id) THEN
        NEW.tags := coalesce((SELECT tags FROM core.entities WHERE guid = NEW.origin_guid), '{}');
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER entities_3a_copy_tags BEFORE INSERT ON core.entities
    FOR EACH ROW EXECUTE FUNCTION core.copy_tags();

-- ---------------------------------------------------------------- rule overrides (D48)
ALTER TABLE core.attribute_values ADD COLUMN rule_override jsonb;
COMMENT ON COLUMN core.attribute_values.rule_override IS
    'Set when the value was saved although it fails validation rules (D48): the rules, their messages and who saved it when';

-- ---------------------------------------------------------------- relationships outside the metamodel (D49)
ALTER TABLE core.allowed_relationships ADD COLUMN from_content boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN core.allowed_relationships.from_content IS
    'Added when someone entering content related two entities the metamodel did not allow (D49); a Model Admin reviews it';

-- Whoever may change a model's content may add a relationship the metamodel does not allow: the mapping
-- is added to the metamodel as a new metamodel version, flagged from_content, for a Model Admin to keep
-- or remove. Returns the metamodel version.
CREATE FUNCTION core.allow_from_content(p_model bigint, p_rel_type bigint, p_source_type bigint, p_target_type bigint)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, core AS $$
DECLARE
    v_why     text := core.why_not(p_model, 'content');
    v_roles   text := current_setting('eax.user_roles', true);
    v_version integer;
BEGIN
    IF v_why IS NOT NULL THEN
        RAISE EXCEPTION 'Not allowed for %: %', core.current_actor(), v_why USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM core.relationship_types WHERE id = p_rel_type AND model_id = p_model AND NOT is_deleted)
       OR NOT EXISTS (SELECT 1 FROM core.entity_types WHERE id = p_source_type AND model_id = p_model AND NOT is_deleted)
       OR NOT EXISTS (SELECT 1 FROM core.entity_types WHERE id = p_target_type AND model_id = p_model AND NOT is_deleted) THEN
        RAISE EXCEPTION 'The relationship type and both entity types must be in this model';
    END IF;
    -- the metamodel change is made for the person, who may change content but not the metamodel
    PERFORM set_config('eax.user_roles', '', true);
    v_version := core.publish_metamodel_version(p_model, 'Relationship allowed from data entry (D49)');
    INSERT INTO core.allowed_relationships (model_id, relationship_type_id, source_type_id, target_type_id, note, from_content)
    VALUES (p_model, p_rel_type, p_source_type, p_target_type,
            'Added from data entry by ' || core.current_actor() || ' (D49)', true)
    ON CONFLICT (relationship_type_id, source_type_id, target_type_id)
        DO UPDATE SET is_deleted = false, from_content = true, note = EXCLUDED.note;
    PERFORM set_config('eax.user_roles', coalesce(v_roles, ''), true);
    RETURN v_version;
END;
$$;
REVOKE ALL ON FUNCTION core.allow_from_content(bigint, bigint, bigint, bigint) FROM PUBLIC;

-- ---------------------------------------------------------------- tags in reports
CREATE FUNCTION rpt.f_entity_tags() RETURNS TABLE (model_id bigint, entity_id bigint, tag text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT e.model_id, e.id, t FROM core.entities e JOIN core.models m ON m.id = e.model_id AND NOT m.is_deleted,
           unnest(e.tags) AS t
     WHERE NOT e.is_deleted;
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;
REVOKE ALL ON FUNCTION rpt.f_entity_tags() FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        GRANT EXECUTE ON FUNCTION rpt.f_entity_tags() TO eax_report;
    END IF;
END;
$$;
CREATE VIEW rpt.entity_tags AS SELECT * FROM rpt.f_entity_tags();
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        GRANT SELECT ON rpt.entity_tags TO eax_report;
    END IF;
END;
$$;
