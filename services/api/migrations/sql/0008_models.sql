-- =====================================================================================
-- EA Explorer phase 4 (version 0.4.0): creating, copying and sharing models
-- Run by Alembic (migrations/versions/0008_models.py). Checked by tests/sql/phase4_checks.sql.
--
--   * Library Admin (D118): a global role that curates the model library: creates library models,
--     publishes (locks) them, promotes models into the library, uploads packages, withdraws them.
--   * models.library_state: '' (a working model), building (a library model or root still being
--     built, editable by its Model Admin), published (locked, in the library), withdrawn (kept for the
--     models built on it, gone from the library). Roots (kind template) and reference models are the
--     library (D81, D101, D119).
--   * Copying a model (D121, MOD-002/003): core.copy_model copies a metamodel, and optionally the content,
--     from one model into another, keeping every row's origin (origin_guid) and display IDs. A copy is
--     faithful: while it runs, the checks that would refuse content the source already holds (retired
--     types, mappings or pick-list values removed since) are not applied to that model.
--   * Deleting a model: Super Admins only, refused while other models are derived from it or built on
--     it; soft (is_deleted), kept in history (D121).
--   * core.metamodel_drafts: metamodels drafted by a language model through MCP (or uploaded), reviewed
--     and applied by a person (D115, D120).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.4.0', '0008_models', 'Phase 4: create, copy and share models; Library Admin; metamodel drafts');

-- ---------------------------------------------------------------- Library Admin (D118)
UPDATE core.app_roles SET sort_order = 7 WHERE code = 'user';
INSERT INTO core.app_roles (code, name, scope, description, sort_order) VALUES
    ('library-admin', 'Library Admin', 'global',
     'Curates the model library: creates library models, publishes them, promotes models into it, uploads packages, withdraws them', 6);
INSERT INTO core.role_mappings (keycloak_role, app_role, created_by)
VALUES ('eax-library-admin', 'library-admin', 'system:migration')
ON CONFLICT DO NOTHING;

-- True when the person asking may curate the library (Library Admins and Super Admins)
CREATE FUNCTION core.may_curate_library() RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT core.session_roles() && ARRAY['library-admin', 'super-admin']
$$;

-- ---------------------------------------------------------------- model columns
ALTER TABLE core.models
    ADD COLUMN library_state text NOT NULL DEFAULT ''
        CHECK (library_state IN ('', 'building', 'published', 'withdrawn')),
    ADD COLUMN copy_state    text NOT NULL DEFAULT '' CHECK (copy_state IN ('', 'copying', 'failed')),
    ADD COLUMN copy_note     text NOT NULL DEFAULT '',      -- what was copied, or why the copy failed
    ADD COLUMN history_from_source boolean NOT NULL DEFAULT false;  -- copied "with history": entities show their source's history
COMMENT ON COLUMN core.models.library_state IS
    ''''' a working model; building: a library model or root being built (editable); published: locked, in the library; withdrawn';

UPDATE core.models SET library_state = CASE WHEN is_locked THEN 'published' ELSE 'building' END
 WHERE kind_code IN ('template', 'reference');

-- A new root or reference model starts as building (published when the installer loads it locked)
CREATE FUNCTION core.default_library_state() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.kind_code IN ('template', 'reference') AND NEW.library_state = '' THEN
        NEW.library_state := CASE WHEN NEW.is_locked THEN 'published' ELSE 'building' END;
    ELSIF NEW.kind_code NOT IN ('template', 'reference') THEN
        NEW.library_state := '';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER models_1_library_state BEFORE INSERT ON core.models
    FOR EACH ROW EXECUTE FUNCTION core.default_library_state();

-- library models and roots carry a state; working models do not
ALTER TABLE core.models ADD CONSTRAINT models_library_state
    CHECK ((kind_code IN ('template', 'reference')) = (library_state <> ''));

-- Whoever creates a model sees it straight away (before their Model Admin role is written, so the
-- INSERT ... RETURNING that creates it can read it back)
DROP POLICY read_by_model ON core.models;
CREATE POLICY read_by_model ON core.models FOR SELECT USING (
    kind_code IN ('template', 'reference') OR core.may_read_model(id)
    OR (created_by = core.current_actor() AND core.session_roles() IS NOT NULL));

-- ---------------------------------------------------------------- locked models (replaces 0003)
-- The installer's login may still do anything. A Library Admin (or Super Admin) may now also publish a
-- library model (lock it), withdraw or restore one (library_state only), and nothing else on a
-- locked model. Everyone else is refused, as before.
CREATE OR REPLACE FUNCTION core.refuse_locked_model() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_same boolean;
BEGIN
    IF core.is_installer() THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'INSERT' AND NEW.is_locked THEN
        RAISE EXCEPTION 'A new model starts unlocked ("%"): a Library Admin publishes it', NEW.name
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.is_locked AND core.may_curate_library() THEN
        v_same := (to_jsonb(NEW) - ARRAY['library_state', 'lifecycle', 'modified_at', 'modified_by', 'row_version'])
                = (to_jsonb(OLD) - ARRAY['library_state', 'lifecycle', 'modified_at', 'modified_by', 'row_version']);
        IF v_same THEN
            RETURN NEW;   -- withdraw or restore a library model
        END IF;
    END IF;
    IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.is_locked THEN
        RAISE EXCEPTION 'Model "%" is locked (read-only) and cannot be changed or deleted', OLD.name
            USING ERRCODE = 'insufficient_privilege',
                  HINT = 'Create a model from it to work on.';
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.is_locked THEN
        IF NOT core.may_curate_library() THEN
            RAISE EXCEPTION 'Only a Library Admin can publish (lock) a model ("%")', NEW.name
                USING ERRCODE = 'insufficient_privilege';
        END IF;
        IF NEW.kind_code NOT IN ('template', 'reference') THEN
            RAISE EXCEPTION 'Only root metamodels and reference models go into the library ("%")', NEW.name;
        END IF;
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

-- ---------------------------------------------------------------- who may change models (replaces 0006)
-- Additions: Library Admins create and change roots and reference models (D118); deleting a model is for
-- Super Admins only (D121); a model under copy accepts the copy's rows from whoever started it.
CREATE OR REPLACE FUNCTION core.refuse_unpermitted() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_model bigint;
    v_part  text := TG_ARGV[0];
    v_why   text;
BEGIN
    IF core.session_roles() IS NULL THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    -- (separate statements: a row of core.models has no model_id field)
    IF TG_TABLE_NAME = 'models' THEN
        IF TG_OP = 'UPDATE' AND NEW.is_deleted AND NOT OLD.is_deleted
           AND NOT ('super-admin' = ANY (core.session_roles())) THEN
            RAISE EXCEPTION 'Not allowed for %: deleting a model needs the Super Admin role', core.current_actor()
                USING ERRCODE = 'insufficient_privilege', HINT = 'Archive it instead.';
        END IF;
        IF NEW.kind_code IN ('template', 'reference') AND core.may_curate_library() THEN
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;   -- the library's curator
        END IF;
        IF TG_OP = 'INSERT' THEN
            -- a new model: judged on the model it comes from (Model Admins may derive from theirs)
            v_part := 'create';
            v_model := coalesce(NEW.parent_model_id, NEW.source_model_id);
            IF NEW.kind_code = 'reference' THEN
                RAISE EXCEPTION 'Not allowed for %: reference models are added to the library by a Library Admin',
                    core.current_actor() USING ERRCODE = 'insufficient_privilege';
            END IF;
            IF NEW.kind_code = 'template' AND 'model-creator' = ANY (core.session_roles()) THEN
                RETURN NEW;   -- Model Creators build roots (MOD-016)
            END IF;
        ELSE
            v_model := CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END;
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        v_model := OLD.model_id;
    ELSE
        v_model := NEW.model_id;
    END IF;
    v_why := core.why_not(v_model, v_part);
    IF v_why IS NOT NULL AND TG_TABLE_NAME = 'model_users' AND TG_OP = 'INSERT' THEN
        -- (nested: NEW.role exists only on model_users rows)
        IF NEW.role = 'model-admin' AND NEW.username = lower(core.current_actor())
           AND core.first_role_by_creator(NEW.model_id) THEN
            v_why := NULL;   -- whoever created a model (allowed above) may make themselves its first Model Admin
        END IF;
    END IF;
    IF v_why IS NOT NULL THEN
        RAISE EXCEPTION 'Not allowed for %: %', core.current_actor(), v_why
            USING ERRCODE = 'insufficient_privilege',
                  HINT = 'Global roles are given in Keycloak; roles on a model on the model''s People tab.';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

-- A model other models are derived from or built on cannot be deleted (archive it instead)
CREATE FUNCTION core.refuse_delete_with_dependants() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_names text;
BEGIN
    IF NEW.is_deleted AND NOT OLD.is_deleted THEN
        SELECT string_agg(name, ', ' ORDER BY name) INTO v_names FROM core.models
         WHERE NOT is_deleted AND id <> NEW.id AND (parent_model_id = NEW.id OR source_model_id = NEW.id);
        IF v_names IS NOT NULL THEN
            RAISE EXCEPTION 'Model "%" cannot be deleted: other models are derived from it or built on it (%)', NEW.name, v_names
                USING ERRCODE = 'object_in_use', HINT = 'Archive it instead, or delete those models first.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER models_2_dependants BEFORE UPDATE OF is_deleted ON core.models
    FOR EACH ROW EXECUTE FUNCTION core.refuse_delete_with_dependants();

-- ---------------------------------------------------------------- faithful copies
-- True while core.copy_model fills this model (set for the transaction only)
CREATE FUNCTION core.copying_into(p_model bigint) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT coalesce(current_setting('eax.copy_into', true), '') = p_model::text
$$;

-- (replaces 0005) a retired type's entities are copied as they are
CREATE OR REPLACE FUNCTION core.refuse_retired_type() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_type   text;
BEGIN
    IF core.is_installer() OR core.copying_into(NEW.model_id) THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.is_deleted AND NOT OLD.is_deleted THEN
        RETURN NEW;   -- removal (kept in history) is allowed
    END IF;
    IF TG_TABLE_NAME = 'entities' THEN
        SELECT name INTO v_type FROM core.entity_types WHERE id = NEW.entity_type_id AND status_code = 'retired';
    ELSIF TG_TABLE_NAME = 'attribute_values' THEN
        SELECT t.name INTO v_type FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
         WHERE e.id = NEW.entity_id AND t.status_code = 'retired';
    ELSE -- relationships: neither end may be of a retired type
        SELECT t.name INTO v_type FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
         WHERE e.id IN (NEW.source_entity_id, NEW.target_entity_id) AND t.status_code = 'retired' LIMIT 1;
    END IF;
    IF v_type IS NOT NULL THEN
        RAISE EXCEPTION 'Entity type "%" is retired: its entities are read-only until the type is restored', v_type
            USING ERRCODE = 'object_in_use', HINT = 'A Model Admin can restore the type on the Metamodel tab.';
    END IF;
    RETURN NEW;
END;
$$;

-- (replaces 0002) a relationship the source holds is copied even if its mapping was removed since
CREATE OR REPLACE FUNCTION core.check_relationship() RETURNS trigger LANGUAGE plpgsql AS $$
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
    IF NOT core.copying_into(NEW.model_id) AND NOT EXISTS (
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

-- (replaces 0002) a value the source holds is copied even if its pick-list value was removed since
CREATE OR REPLACE FUNCTION core.check_attribute_value() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_attr    core.attribute_types%ROWTYPE;
    v_storage text;
    v_owner_model bigint;
    v_owner_type  bigint;
    v_copy    boolean := core.copying_into(NEW.model_id);
BEGIN
    SELECT * INTO v_attr FROM core.attribute_types WHERE id = NEW.attribute_type_id;
    SELECT storage INTO v_storage FROM core.data_types WHERE code = v_attr.data_type_code;
    IF v_attr.model_id <> NEW.model_id THEN
        RAISE EXCEPTION 'Attribute % belongs to another model', v_attr.code;
    END IF;
    -- the attribute must be mapped to the owner's type
    IF NEW.entity_id IS NOT NULL THEN
        SELECT model_id, entity_type_id INTO v_owner_model, v_owner_type FROM core.entities WHERE id = NEW.entity_id;
        IF NOT v_copy AND NOT EXISTS (SELECT 1 FROM core.item_attributes WHERE entity_type_id = v_owner_type
                         AND attribute_type_id = NEW.attribute_type_id AND NOT is_deleted) THEN
            RAISE EXCEPTION 'Attribute % does not apply to this entity''s type', v_attr.name;
        END IF;
    ELSE
        SELECT model_id, relationship_type_id INTO v_owner_model, v_owner_type FROM core.relationships WHERE id = NEW.relationship_id;
        IF NOT v_copy AND NOT EXISTS (SELECT 1 FROM core.item_attributes WHERE relationship_type_id = v_owner_type
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
    IF NOT v_copy AND v_attr.pick_list_id IS NOT NULL AND NEW.value_text IS NOT NULL AND NOT EXISTS (
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

-- Copies the metamodel of p_src into p_dst (which must have none yet), and with p_content its entities,
-- values and relationships. Every copied row keeps the row it came from in origin_guid; entities keep
-- their display IDs (and the counters follow). Runs with the caller's rights: the database checks they
-- may change p_dst (its Model Admin) and read p_src. Returns how many rows of each kind were copied.
CREATE FUNCTION core.copy_model(p_src bigint, p_dst bigint, p_content boolean) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    n jsonb := '{}'::jsonb;
    c integer;
BEGIN
    IF EXISTS (SELECT 1 FROM core.entity_types WHERE model_id = p_dst) THEN
        RAISE EXCEPTION 'The model to copy into already has a metamodel';
    END IF;
    PERFORM set_config('eax.copy_into', p_dst::text, true);

    INSERT INTO core.layers (model_id, code, name, description, colour, sort_order, origin_guid, status_code)
    SELECT p_dst, code, name, description, colour, sort_order, guid, status_code
      FROM core.layers WHERE model_id = p_src AND NOT is_deleted;
    GET DIAGNOSTICS c = ROW_COUNT; n := n || jsonb_build_object('layers', c);

    INSERT INTO core.pick_lists (model_id, code, name, description, origin_guid, status_code)
    SELECT p_dst, code, name, description, guid, status_code FROM core.pick_lists WHERE model_id = p_src AND NOT is_deleted;
    GET DIAGNOSTICS c = ROW_COUNT; n := n || jsonb_build_object('pick_lists', c);

    INSERT INTO core.pick_list_values (model_id, pick_list_id, value, description, sort_order, origin_guid, status_code)
    SELECT p_dst, d.id, v.value, v.description, v.sort_order, v.guid, v.status_code
      FROM core.pick_list_values v JOIN core.pick_lists d ON d.model_id = p_dst AND d.origin_guid =
           (SELECT guid FROM core.pick_lists WHERE id = v.pick_list_id)
     WHERE v.model_id = p_src AND NOT v.is_deleted;

    INSERT INTO core.entity_types (model_id, layer_id, code, name, description, aspect, id_prefix, table_name, sort_order,
                                   origin_guid, status_code)
    SELECT p_dst, dl.id, t.code, t.name, t.description, t.aspect, t.id_prefix, t.table_name, t.sort_order, t.guid, t.status_code
      FROM core.entity_types t JOIN core.layers sl ON sl.id = t.layer_id
      JOIN core.layers dl ON dl.model_id = p_dst AND dl.origin_guid = sl.guid
     WHERE t.model_id = p_src AND NOT t.is_deleted;
    GET DIAGNOSTICS c = ROW_COUNT; n := n || jsonb_build_object('entity_types', c);

    INSERT INTO core.relationship_types (model_id, code, name, verb, category, is_directed, description, sort_order,
                                         origin_guid, status_code)
    SELECT p_dst, code, name, verb, category, is_directed, description, sort_order, guid, status_code
      FROM core.relationship_types WHERE model_id = p_src AND NOT is_deleted;
    GET DIAGNOSTICS c = ROW_COUNT; n := n || jsonb_build_object('relationship_types', c);

    INSERT INTO core.attribute_types (model_id, code, name, description, data_type_code, pick_list_id, unit, column_name,
                                      origin_guid, status_code)
    SELECT p_dst, a.code, a.name, a.description, a.data_type_code, dp.id, a.unit, a.column_name, a.guid, a.status_code
      FROM core.attribute_types a
      LEFT JOIN core.pick_lists sp ON sp.id = a.pick_list_id
      LEFT JOIN core.pick_lists dp ON dp.model_id = p_dst AND dp.origin_guid = sp.guid
     WHERE a.model_id = p_src AND NOT a.is_deleted;
    GET DIAGNOSTICS c = ROW_COUNT; n := n || jsonb_build_object('attribute_types', c);

    INSERT INTO core.item_attributes (model_id, attribute_type_id, entity_type_id, relationship_type_id, is_required,
                                      section, sort_order, default_value, help_text, origin_guid, status_code)
    SELECT p_dst, da.id, de.id, dr.id, i.is_required, i.section, i.sort_order, i.default_value, i.help_text, i.guid, i.status_code
      FROM core.item_attributes i
      JOIN core.attribute_types sa ON sa.id = i.attribute_type_id
      JOIN core.attribute_types da ON da.model_id = p_dst AND da.origin_guid = sa.guid
      LEFT JOIN core.entity_types se ON se.id = i.entity_type_id
      LEFT JOIN core.entity_types de ON de.model_id = p_dst AND de.origin_guid = se.guid
      LEFT JOIN core.relationship_types sr ON sr.id = i.relationship_type_id
      LEFT JOIN core.relationship_types dr ON dr.model_id = p_dst AND dr.origin_guid = sr.guid
     WHERE i.model_id = p_src AND NOT i.is_deleted
       AND (i.entity_type_id IS NULL OR de.id IS NOT NULL) AND (i.relationship_type_id IS NULL OR dr.id IS NOT NULL);

    INSERT INTO core.validation_rules (model_id, attribute_type_id, field_name, entity_type_id, rule_type_code, param1, param2,
                                       severity, message, sort_order, origin_guid, status_code)
    SELECT p_dst, da.id, r.field_name, de.id, r.rule_type_code, r.param1, r.param2, r.severity, r.message, r.sort_order,
           r.guid, r.status_code
      FROM core.validation_rules r
      LEFT JOIN core.attribute_types sa ON sa.id = r.attribute_type_id
      LEFT JOIN core.attribute_types da ON da.model_id = p_dst AND da.origin_guid = sa.guid
      LEFT JOIN core.entity_types se ON se.id = r.entity_type_id
      LEFT JOIN core.entity_types de ON de.model_id = p_dst AND de.origin_guid = se.guid
     WHERE r.model_id = p_src AND NOT r.is_deleted
       AND (r.attribute_type_id IS NULL OR da.id IS NOT NULL) AND (r.entity_type_id IS NULL OR de.id IS NOT NULL);
    GET DIAGNOSTICS c = ROW_COUNT; n := n || jsonb_build_object('rules', c);

    INSERT INTO core.allowed_relationships (model_id, relationship_type_id, source_type_id, target_type_id, note,
                                            origin_guid, status_code)
    SELECT p_dst, dr.id, ds.id, dt.id, a.note, a.guid, a.status_code
      FROM core.allowed_relationships a
      JOIN core.relationship_types sr ON sr.id = a.relationship_type_id
      JOIN core.relationship_types dr ON dr.model_id = p_dst AND dr.origin_guid = sr.guid
      JOIN core.entity_types ss ON ss.id = a.source_type_id
      JOIN core.entity_types ds ON ds.model_id = p_dst AND ds.origin_guid = ss.guid
      JOIN core.entity_types st ON st.id = a.target_type_id
      JOIN core.entity_types dt ON dt.model_id = p_dst AND dt.origin_guid = st.guid
     WHERE a.model_id = p_src AND NOT a.is_deleted;
    GET DIAGNOSTICS c = ROW_COUNT; n := n || jsonb_build_object('mappings', c);

    IF p_content THEN
        INSERT INTO core.entities (model_id, entity_type_id, display_id, name, description, origin_guid, status_code)
        SELECT p_dst, dt.id, e.display_id, e.name, e.description, e.guid, e.status_code
          FROM core.entities e JOIN core.entity_types st ON st.id = e.entity_type_id
          JOIN core.entity_types dt ON dt.model_id = p_dst AND dt.origin_guid = st.guid
         WHERE e.model_id = p_src AND NOT e.is_deleted;
        GET DIAGNOSTICS c = ROW_COUNT; n := n || jsonb_build_object('entities', c);

        -- parents once every entity is there
        UPDATE core.entities d SET parent_entity_id = dp.id
          FROM core.entities s
          JOIN core.entities sp ON sp.id = s.parent_entity_id
          JOIN core.entities dp ON dp.model_id = p_dst AND dp.origin_guid = sp.guid
         WHERE d.model_id = p_dst AND d.origin_guid = s.guid AND s.model_id = p_src AND s.parent_entity_id IS NOT NULL;

        INSERT INTO core.display_id_counters (model_id, entity_type_id, last_number, origin_guid)
        SELECT p_dst, dt.id, k.last_number, k.guid
          FROM core.display_id_counters k JOIN core.entity_types st ON st.id = k.entity_type_id
          JOIN core.entity_types dt ON dt.model_id = p_dst AND dt.origin_guid = st.guid
         WHERE k.model_id = p_src
        ON CONFLICT (model_id, entity_type_id) DO UPDATE SET last_number = greatest(core.display_id_counters.last_number,
                                                                                    EXCLUDED.last_number);

        INSERT INTO core.relationships (model_id, relationship_type_id, source_entity_id, target_entity_id, name, description,
                                        origin_guid, status_code)
        SELECT p_dst, dr.id, ds.id, dt.id, r.name, r.description, r.guid, r.status_code
          FROM core.relationships r
          JOIN core.relationship_types sr ON sr.id = r.relationship_type_id
          JOIN core.relationship_types dr ON dr.model_id = p_dst AND dr.origin_guid = sr.guid
          JOIN core.entities se ON se.id = r.source_entity_id AND NOT se.is_deleted
          JOIN core.entities ds ON ds.model_id = p_dst AND ds.origin_guid = se.guid
          JOIN core.entities te ON te.id = r.target_entity_id AND NOT te.is_deleted
          JOIN core.entities dt ON dt.model_id = p_dst AND dt.origin_guid = te.guid
         WHERE r.model_id = p_src AND NOT r.is_deleted;
        GET DIAGNOSTICS c = ROW_COUNT; n := n || jsonb_build_object('relationships', c);

        INSERT INTO core.attribute_values (model_id, attribute_type_id, entity_id, relationship_id, value_text, value_number,
                                           value_date, value_bool, value_ref, origin_guid, status_code)
        SELECT p_dst, da.id, de.id, dr.id, v.value_text, v.value_number, v.value_date, v.value_bool, dref.id, v.guid, v.status_code
          FROM core.attribute_values v
          JOIN core.attribute_types sa ON sa.id = v.attribute_type_id
          JOIN core.attribute_types da ON da.model_id = p_dst AND da.origin_guid = sa.guid
          LEFT JOIN core.entities se ON se.id = v.entity_id
          LEFT JOIN core.entities de ON de.model_id = p_dst AND de.origin_guid = se.guid
          LEFT JOIN core.relationships sr ON sr.id = v.relationship_id
          LEFT JOIN core.relationships dr ON dr.model_id = p_dst AND dr.origin_guid = sr.guid
          LEFT JOIN core.entities sref ON sref.id = v.value_ref
          LEFT JOIN core.entities dref ON dref.model_id = p_dst AND dref.origin_guid = sref.guid
         WHERE v.model_id = p_src AND NOT v.is_deleted
           AND (v.entity_id IS NULL OR de.id IS NOT NULL) AND (v.relationship_id IS NULL OR dr.id IS NOT NULL)
           AND (v.value_ref IS NULL OR dref.id IS NOT NULL);
        GET DIAGNOSTICS c = ROW_COUNT; n := n || jsonb_build_object('values', c);
    END IF;

    PERFORM set_config('eax.copy_into', '', true);
    RETURN n;
END;
$$;

-- ---------------------------------------------------------------- metamodel drafts (D115, D120)
CREATE TABLE core.metamodel_drafts (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid          uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    name          text NOT NULL CHECK (name <> ''),
    kind          text NOT NULL CHECK (kind IN ('root', 'changes')),      -- a new root metamodel, or changes to a model
    base_model_id bigint REFERENCES core.models (id),     -- root: the root it starts from (Root: from scratch)
    target_model_id bigint REFERENCES core.models (id),   -- changes: the model they apply to
    spec          jsonb NOT NULL DEFAULT '{}'::jsonb,     -- the metamodel, in the package format (eax-metamodel/1)
    checks        jsonb NOT NULL DEFAULT '[]'::jsonb,     -- the last check's findings
    status        text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'applied', 'rejected')),
    note          text NOT NULL DEFAULT '',               -- what the person asked for, or why it was rejected
    proposed_via  text NOT NULL DEFAULT 'mcp' CHECK (proposed_via IN ('mcp', 'upload', 'screen')),
    proposed_by   text NOT NULL DEFAULT core.current_actor(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    modified_at   timestamptz NOT NULL DEFAULT now(),
    decided_at    timestamptz,
    decided_by    text,
    applied_model_id bigint REFERENCES core.models (id),
    CHECK ((kind = 'changes') = (target_model_id IS NOT NULL))
);
CREATE INDEX metamodel_drafts_by_idx ON core.metamodel_drafts (proposed_by, status);
COMMENT ON TABLE core.metamodel_drafts IS 'Metamodels drafted by a language model (MCP) or uploaded, waiting for a person to review and apply them (D115)';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT ON core.metamodel_drafts TO eax_migrator;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        REVOKE ALL ON core.metamodel_drafts FROM eax_report;
    END IF;
END;
$$;
