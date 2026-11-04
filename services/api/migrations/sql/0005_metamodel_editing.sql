-- =====================================================================================
-- EA Explorer phase 3 (version 0.3.0): metamodel editing, metamodel versions, model locks
-- Run by Alembic (migrations/versions/0005_metamodel_editing.py). Checked by
-- tests/sql/phase3_checks.sql.
--
--   * core.metamodel_versions: one row per published metamodel version of a model. Every change
--     made in the metamodel editor publishes a new version at once (D72), with a short note.
--   * Entities record the metamodel version they were created in and last changed in (D65).
--   * Attributes on an entity type carry a default value for new entities (D64).
--   * Entities of a retired entity type are read-only until it is restored (D87).
--   * Model locks set and lifted by Model Admins (D67): metamodel, content (metamodel and
--     content) and maintenance (only the person who set it may change the model; from phase 3.1
--     any Model Admin). Different from is_locked, the installer's permanent lock.
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.3.0', '0005_metamodel_editing', 'Phase 3: metamodel editing, metamodel versions and history, model locks');

-- ---------------------------------------------------------------- metamodel versions
CREATE TABLE core.metamodel_versions (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id    bigint NOT NULL REFERENCES core.models (id),
    version     integer NOT NULL CHECK (version > 0),
    note        text NOT NULL DEFAULT '',                 -- what the change was, in a few words
    changed_at  timestamptz NOT NULL DEFAULT now(),
    changed_by  text NOT NULL DEFAULT core.current_actor(),
    UNIQUE (model_id, version)
);
CREATE INDEX metamodel_versions_model_idx ON core.metamodel_versions (model_id, changed_at);

-- every existing model starts with the version it has (its first publication), dated at its creation
INSERT INTO core.metamodel_versions (model_id, version, note, changed_at, changed_by)
SELECT id, metamodel_version, 'Initial metamodel', created_at, created_by FROM core.models;

-- A model created later (the seed runs after the migrations; copies from phase 4) starts at its
-- first version too
CREATE FUNCTION core.first_metamodel_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO core.metamodel_versions (model_id, version, note, changed_at, changed_by)
    VALUES (NEW.id, NEW.metamodel_version, 'Initial metamodel', NEW.created_at, NEW.created_by);
    RETURN NULL;
END;
$$;
CREATE TRIGGER models_first_metamodel_version AFTER INSERT ON core.models
    FOR EACH ROW EXECUTE FUNCTION core.first_metamodel_version();

-- The next version of a model's metamodel: bumps models.metamodel_version, writes the version row
-- and labels this transaction's history rows "metamodel vN" (": note" when a note is given). Returns N.
CREATE FUNCTION core.publish_metamodel_version(p_model bigint, p_note text) RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    v integer;
BEGIN
    UPDATE core.models SET metamodel_version = metamodel_version + 1
     WHERE id = p_model RETURNING metamodel_version INTO v;
    IF v IS NULL THEN
        RAISE EXCEPTION 'No model %', p_model;
    END IF;
    INSERT INTO core.metamodel_versions (model_id, version, note) VALUES (p_model, v, coalesce(p_note, ''));
    PERFORM set_config('eax.history_label',
        'metamodel v' || v || CASE WHEN coalesce(p_note, '') <> '' THEN ': ' || left(p_note, 200) ELSE '' END, true);
    RETURN v;
END;
$$;

-- The metamodel version in force at a moment (for history rows written without a label)
CREATE FUNCTION core.metamodel_version_at(p_model bigint, p_at timestamptz) RETURNS integer
LANGUAGE sql STABLE AS $$
    SELECT coalesce(max(version), 1) FROM core.metamodel_versions WHERE model_id = p_model AND changed_at <= p_at
$$;

-- ---------------------------------------------------------------- defaults for attributes
ALTER TABLE core.item_attributes
    ADD COLUMN default_value text,          -- given to new entities of the type (empty: none)
    ADD COLUMN help_text     text NOT NULL DEFAULT '';

-- ---------------------------------------------------------------- metamodel versions on entities
ALTER TABLE core.entities
    ADD COLUMN created_mm_version  integer,  -- the metamodel version the entity was created in
    ADD COLUMN modified_mm_version integer;  -- the metamodel version it was last changed in

-- the existing triggers must not count this backfill as a change by anyone
ALTER TABLE core.entities DISABLE TRIGGER entities_stamp;
ALTER TABLE core.entities DISABLE TRIGGER entities_history;
ALTER TABLE core.entities DISABLE TRIGGER entities_check;
DO $$
BEGIN
    -- locked models refuse changes; this backfill is part of the product's own migration
    ALTER TABLE core.entities DISABLE TRIGGER entities_0_lock;
EXCEPTION WHEN undefined_object THEN NULL;
END $$;
UPDATE core.entities e SET created_mm_version = m.metamodel_version, modified_mm_version = m.metamodel_version
  FROM core.models m WHERE m.id = e.model_id;
DO $$
BEGIN
    ALTER TABLE core.entities ENABLE TRIGGER entities_0_lock;
EXCEPTION WHEN undefined_object THEN NULL;
END $$;
ALTER TABLE core.entities ENABLE TRIGGER entities_check;
ALTER TABLE core.entities ENABLE TRIGGER entities_history;
ALTER TABLE core.entities ENABLE TRIGGER entities_stamp;

CREATE FUNCTION core.stamp_mm_version() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v integer;
BEGIN
    SELECT metamodel_version INTO v FROM core.models WHERE id = NEW.model_id;
    IF TG_OP = 'INSERT' THEN
        NEW.created_mm_version := coalesce(NEW.created_mm_version, v);
    ELSE
        NEW.created_mm_version := OLD.created_mm_version;
    END IF;
    NEW.modified_mm_version := v;
    RETURN NEW;
END;
$$;
CREATE TRIGGER entities_mm_version BEFORE INSERT OR UPDATE ON core.entities
    FOR EACH ROW EXECUTE FUNCTION core.stamp_mm_version();

-- ---------------------------------------------------------------- model locks (D67)
ALTER TABLE core.models
    ADD COLUMN lock_level  text NOT NULL DEFAULT 'none'
        CHECK (lock_level IN ('none', 'metamodel', 'content', 'maintenance')),
    ADD COLUMN lock_reason text NOT NULL DEFAULT '',
    ADD COLUMN locked_at   timestamptz,
    ADD COLUMN locked_by   text;

COMMENT ON COLUMN core.models.lock_level IS
    'none; metamodel (metamodel read-only); content (metamodel and content read-only); '
    'maintenance (only the person who set it may change the model: Model Admins from phase 3.1)';

-- Refuses changes to the metamodel part (TG_ARGV[0] = metamodel) or the content part
-- (TG_ARGV[0] = content) of a model under a lock. The installer's login passes.
CREATE FUNCTION core.refuse_model_lock() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_model  bigint := CASE WHEN TG_OP = 'DELETE' THEN OLD.model_id ELSE NEW.model_id END;
    v        record;
    v_part   text := TG_ARGV[0];
BEGIN
    IF core.is_installer() THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    SELECT name, lock_level, lock_reason, locked_by INTO v FROM core.models WHERE id = v_model;
    IF v.lock_level = 'none' OR (v_part = 'content' AND v.lock_level = 'metamodel') THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF v.lock_level = 'maintenance' AND v.locked_by = core.current_actor() THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    RAISE EXCEPTION '%', CASE v.lock_level
            WHEN 'metamodel' THEN format('The metamodel of model "%s" is locked by %s: it cannot be changed until a Model Admin unlocks it', v.name, v.locked_by)
            WHEN 'content' THEN format('Model "%s" is locked by %s (metamodel and content): nothing can be changed until a Model Admin unlocks it', v.name, v.locked_by)
            ELSE format('Model "%s" is under maintenance by %s: only they can change it until the lock is lifted', v.name, v.locked_by) END
        USING ERRCODE = 'object_in_use',
              DETAIL = 'Reason: ' || coalesce(nullif(v.lock_reason, ''), 'none given'),
              HINT = 'A Model Admin can lift the lock from the model page.';
END;
$$;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['layers', 'entity_types', 'relationship_types', 'pick_lists', 'pick_list_values',
                             'attribute_types', 'item_attributes', 'validation_rules', 'allowed_relationships'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON core.%I
                        FOR EACH ROW EXECUTE FUNCTION core.refuse_model_lock(''metamodel'')', t || '_1_model_lock', t);
    END LOOP;
    FOREACH t IN ARRAY ARRAY['entities', 'relationships', 'attribute_values', 'display_id_counters'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON core.%I
                        FOR EACH ROW EXECUTE FUNCTION core.refuse_model_lock(''content'')', t || '_1_model_lock', t);
    END LOOP;
END;
$$;

-- A metamodel version cannot be published while the metamodel is locked (the editor's first step)
CREATE FUNCTION core.refuse_version_under_lock() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v record;
BEGIN
    IF core.is_installer() THEN
        RETURN NEW;
    END IF;
    SELECT name, lock_level, locked_by INTO v FROM core.models WHERE id = NEW.model_id;
    IF v.lock_level IN ('metamodel', 'content') OR (v.lock_level = 'maintenance' AND v.locked_by <> core.current_actor()) THEN
        RAISE EXCEPTION 'The metamodel of model "%" is locked (%) by %: it cannot be changed', v.name, v.lock_level, v.locked_by
            USING ERRCODE = 'object_in_use', HINT = 'A Model Admin can lift the lock from the model page.';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER metamodel_versions_lock BEFORE INSERT ON core.metamodel_versions
    FOR EACH ROW EXECUTE FUNCTION core.refuse_version_under_lock();

-- Locks belong to working models: templates and reference models carry the installer's lock.
CREATE FUNCTION core.check_model_lock() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.lock_level IS DISTINCT FROM OLD.lock_level THEN
        IF NEW.lock_level <> 'none' AND OLD.lock_level <> 'none' THEN
            RAISE EXCEPTION 'Model "%" is already locked (%): unlock it first', NEW.name, OLD.lock_level;
        END IF;
        IF NEW.lock_level = 'none' THEN
            NEW.lock_reason := ''; NEW.locked_at := NULL; NEW.locked_by := NULL;
        ELSE
            NEW.locked_at := now(); NEW.locked_by := core.current_actor();
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER models_1_lock_level BEFORE UPDATE OF lock_level ON core.models
    FOR EACH ROW EXECUTE FUNCTION core.check_model_lock();

-- ---------------------------------------------------------------- retired entity types (D87)
-- A retired entity type offers no new entities and its entities are read-only until the type is
-- restored. Removing values or relationships (setting is_deleted) is still allowed, so removing an
-- attribute or a relationship type works across retired types too. The installer's login passes.
CREATE FUNCTION core.refuse_retired_type() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_entity bigint;
    v_type   text;
BEGIN
    IF core.is_installer() THEN
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
CREATE TRIGGER entities_2_retired BEFORE INSERT OR UPDATE ON core.entities
    FOR EACH ROW EXECUTE FUNCTION core.refuse_retired_type();
CREATE TRIGGER attribute_values_2_retired BEFORE INSERT OR UPDATE ON core.attribute_values
    FOR EACH ROW EXECUTE FUNCTION core.refuse_retired_type();
CREATE TRIGGER relationships_2_retired BEFORE INSERT OR UPDATE ON core.relationships
    FOR EACH ROW EXECUTE FUNCTION core.refuse_retired_type();

-- ---------------------------------------------------------------- rights for the installer
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.metamodel_versions TO eax_migrator;
    END IF;
END;
$$;
