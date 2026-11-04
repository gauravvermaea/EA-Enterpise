-- =====================================================================================
-- EA Explorer phase 2: schema versions, model properties, locked reference models
-- Run by Alembic (migrations/versions/0003_library.py) when the api container starts.
-- Checked by tests/sql/phase2_checks.sql.
-- =====================================================================================

-- ---------------------------------------------------------------- schema versions
-- Every migration that moves the version adds a row here. The API's version (version.toml) must
-- equal core.schema_version(); the heartbeat warns when they differ.
CREATE TABLE core.schema_versions (
    version     text PRIMARY KEY CHECK (version ~ '^\d+\.\d+\.\d+$'),
    migration   text NOT NULL,                   -- the Alembic revision that wrote it
    description text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    applied_by  text NOT NULL DEFAULT current_user
);

CREATE FUNCTION core.schema_version() RETURNS text LANGUAGE sql STABLE AS $$
    SELECT version FROM core.schema_versions
     ORDER BY string_to_array(version, '.')::int[] DESC LIMIT 1
$$;

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.1.0', '0002_metamodel', 'Phase 1: metamodel store, generic content, get_entity, history'),
    ('0.2.0', '0003_library',   'Phase 2: schema versions, model properties, locked reference models');

-- ---------------------------------------------------------------- model properties
ALTER TABLE core.models
    ADD COLUMN owner         text NOT NULL DEFAULT '',          -- accountable person or team
    ADD COLUMN lifecycle     text NOT NULL DEFAULT 'active' CHECK (lifecycle IN ('active', 'archived')),
    ADD COLUMN industry      text NOT NULL DEFAULT '',          -- reference models: for example Insurance
    ADD COLUMN version_label text NOT NULL DEFAULT '';          -- reference models: their release, for example 1.0

-- Two versions of a reference model sit side by side: the name is unique per version label.
DROP INDEX core.models_name_uq;
CREATE UNIQUE INDEX models_name_uq ON core.models (lower(name), version_label) WHERE NOT is_deleted;

-- ---------------------------------------------------------------- locked models
-- A locked model (templates and reference models) can be loaded and changed only by the
-- installer's login, eax_migrator, which the seed step uses. Everyone else is refused,
-- administrators and the postgres superuser included, whatever the route: screens, API, MCP,
-- CSV loads or plain SQL. session_user is checked, so SET ROLE does not get round it.
CREATE FUNCTION core.is_installer() RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT session_user::text = 'eax_migrator'
$$;

CREATE FUNCTION core.refuse_locked_model() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF core.is_installer() THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'INSERT' AND NEW.is_locked THEN
        RAISE EXCEPTION 'Only the product installer can add a locked model ("%")', NEW.name
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.is_locked THEN
        RAISE EXCEPTION 'Model "%" is locked (read-only) and cannot be changed or deleted', OLD.name
            USING ERRCODE = 'insufficient_privilege',
                  HINT = 'Make a copy of it to work on (build phase 4).';
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.is_locked THEN
        RAISE EXCEPTION 'Only the product installer can lock a model ("%")', NEW.name
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

-- Metamodel and content rows of a locked model
CREATE FUNCTION core.refuse_locked_content() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_name text;
BEGIN
    IF core.is_installer() THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    SELECT m.name INTO v_name FROM core.models m
     WHERE m.is_locked
       AND m.id IN (CASE WHEN TG_OP <> 'DELETE' THEN NEW.model_id END,
                    CASE WHEN TG_OP <> 'INSERT' THEN OLD.model_id END)
     LIMIT 1;
    IF v_name IS NOT NULL THEN
        RAISE EXCEPTION 'Model "%" is locked (read-only): its % cannot be changed', v_name, replace(TG_TABLE_NAME, '_', ' ')
            USING ERRCODE = 'insufficient_privilege',
                  HINT = 'Make a copy of the model to work on (build phase 4).';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

-- TRUNCATE would empty locked models along with everything else
CREATE FUNCTION core.refuse_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT core.is_installer() THEN
        RAISE EXCEPTION 'TRUNCATE of % is not allowed: it would empty locked models', TG_TABLE_NAME
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NULL;
END;
$$;

-- "0_lock" sorts before the other BEFORE triggers ("check", "stamp"), so a locked model's
-- refusal is the message the user sees.
CREATE TRIGGER models_0_lock BEFORE INSERT OR UPDATE OR DELETE ON core.models
    FOR EACH ROW EXECUTE FUNCTION core.refuse_locked_model();
CREATE TRIGGER models_0_no_truncate BEFORE TRUNCATE ON core.models
    FOR EACH STATEMENT EXECUTE FUNCTION core.refuse_truncate();

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['layers', 'entity_types', 'relationship_types', 'pick_lists', 'pick_list_values',
                             'attribute_types', 'item_attributes', 'validation_rules', 'allowed_relationships',
                             'entities', 'relationships', 'attribute_values', 'display_id_counters'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON core.%I
                        FOR EACH ROW EXECUTE FUNCTION core.refuse_locked_content()', t || '_0_lock', t);
        EXECUTE format('CREATE TRIGGER %I BEFORE TRUNCATE ON core.%I
                        FOR EACH STATEMENT EXECUTE FUNCTION core.refuse_truncate()', t || '_0_no_truncate', t);
    END LOOP;
END;
$$;

-- ---------------------------------------------------------------- the installer's login
-- eax_migrator is created by deploy/postgres/initdb/01-databases.sh with the database. It gets
-- the data rights it needs to load reference models; tables added by later migrations follow
-- through the default privileges.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT USAGE ON SCHEMA core, history, eax TO eax_migrator;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core TO eax_migrator;
        GRANT SELECT, INSERT ON history.row_versions TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core, history TO eax_migrator;
        ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO eax_migrator;
        ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT USAGE, SELECT ON SEQUENCES TO eax_migrator;
    ELSE
        RAISE WARNING 'Role eax_migrator is missing: reference models cannot be loaded. Rebuild from clean (eax clean-run).';
    END IF;
END;
$$;
