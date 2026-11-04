-- =====================================================================================
-- EA Explorer phase 3.1 (version 0.3.1): roles and permissions, enforced by the database
-- Run by Alembic (migrations/versions/0006_roles.py). Checked by tests/sql/phase3_1_checks.sql.
--
--   * Global roles are given in Keycloak (D92, D96): Super Admin, IT Admin, User Admin, Keycloak Admin,
--     Model Creator and User (everyone who may sign in). core.role_mappings maps Keycloak roles to
--     them (defaults: eax-super-admin to super-admin and so on).
--   * Model roles are given per model in EA Explorer (D96): Model Admin, Architect, Model Sub Admin and
--     Report Viewer, in core.model_users. One person can be Architect on one model and Model Admin on
--     another, and hold several roles on one model. Roles are not copied to derived models.
--   * core.model_ancestors: every model's ancestors (parent and source, any depth); anyone with a role
--     on a model reads the models it comes from (D60).
--   * The API tells the database who is asking, for each connection: eax.actor (user name) and
--     eax.user_roles (their global roles). With no user (the installer, the seed, the job runner, psql
--     as an administrator) nothing below restricts anything.
--   * Reading (row-level security): Super Admins read every model; everyone else the models where they
--     have a role, those models' ancestors, and the library (templates and reference models, D98).
--   * Writing (triggers): see core.why_not.
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.3.1', '0006_roles', 'Phase 3.1: global roles from Keycloak, model roles per model, row-level security');

-- ---------------------------------------------------------------- the model hierarchy (D81)
-- Templates are root metamodels: the shipped ones (the Root model at the top, ArchiMate 4) are
-- locked; an organisation's own roots, created from Root or from another root, are changed by their
-- Model Admins until locked. Every root metamodel sits under the Root model.
UPDATE core.model_kinds SET name = 'Root metamodel',
       description = 'A metamodel with no content, at the top of a family of models; new models start from it'
 WHERE code = 'template';

-- ---------------------------------------------------------------- roles
CREATE TABLE core.app_roles (
    code        text PRIMARY KEY,
    name        text NOT NULL,
    scope       text NOT NULL CHECK (scope IN ('global', 'model')),   -- global: from Keycloak; model: per model
    description text NOT NULL,
    sort_order  integer NOT NULL
);
INSERT INTO core.app_roles (code, name, scope, description, sort_order) VALUES
    ('super-admin',        'Super Admin',        'global', 'Everything, everywhere', 1),
    ('it-admin',           'IT Admin',           'global', 'Runs the installation: health, backups, jobs, logs, the SQL window, Superset and Mayan administration; no model content', 2),
    ('user-admin',         'User Admin',         'global', 'Sees people, their roles and which models they have roles on; maps Keycloak roles to global roles; reads no model', 3),
    ('keycloak-admin',     'Keycloak Admin',     'global', 'Administers Keycloak: users, roles, identity providers', 4),
    ('model-creator',      'Model Creator',      'global', 'Creates models, and becomes the Model Admin of each model they create', 5),
    ('user',               'User',               'global', 'May sign in; sees the models where they have a model role', 6),
    ('model-admin',        'Model Admin',        'model',  'Owns this model: changes its metamodel, locks it, gives people roles on it, changes its content, derives models from it; commits (commits phase)', 11),
    ('model-sub-admin',    'Model Sub Admin',    'model',  'The Model Admin''s deputy for content: changes this model''s content; reviews and commits others'' changes (commits phase); not the metamodel or people', 12),
    ('architect',          'Architect',          'model',  'Works on this model''s content: reads and changes entities, relationships and values; changes go for review once commits exist', 13),
    ('report-viewer',      'Report Viewer',      'model',  'Reads this model: screens, pictures, reports and exports; changes nothing', 14);

-- Keycloak role -> global role. Several Keycloak roles may give one global role.
CREATE TABLE core.role_mappings (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid           uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    keycloak_role  text NOT NULL CHECK (keycloak_role <> ''),
    app_role       text NOT NULL REFERENCES core.app_roles (code),
    created_at     timestamptz NOT NULL DEFAULT now(),
    created_by     text NOT NULL DEFAULT core.current_actor(),
    UNIQUE (keycloak_role, app_role)
);
COMMENT ON TABLE core.role_mappings IS 'Which Keycloak role gives which global EA Explorer role (D92)';
CREATE FUNCTION core.check_global_role() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT scope FROM core.app_roles WHERE code = NEW.app_role) <> 'global' THEN
        RAISE EXCEPTION '% is a model role: it is given per model on the model''s People tab, not mapped from Keycloak', NEW.app_role;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER role_mappings_global BEFORE INSERT OR UPDATE ON core.role_mappings
    FOR EACH ROW EXECUTE FUNCTION core.check_global_role();
-- the defaults: the realm roles the installer creates in Keycloak (deploy/keycloak/realm-eaexplorer.json.tmpl)
INSERT INTO core.role_mappings (keycloak_role, app_role, created_by)
SELECT 'eax-' || code, code, 'system:install' FROM core.app_roles WHERE scope = 'global';

-- ---------------------------------------------------------------- who is asking
CREATE FUNCTION core.session_roles() RETURNS text[] LANGUAGE sql STABLE AS $$
    SELECT string_to_array(nullif(current_setting('eax.user_roles', true), ''), ',')
$$;

-- True when no user is set (installer, seed, jobs, an administrator's psql) or the user reads every model
CREATE FUNCTION core.sees_every_model() RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT core.session_roles() IS NULL
        OR 'super-admin' = ANY (core.session_roles())
$$;

-- ---------------------------------------------------------------- model roles (D96)
CREATE TABLE core.model_users (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id    bigint NOT NULL REFERENCES core.models (id),
    username    text NOT NULL CHECK (username = lower(username) AND username <> ''),
    role        text NOT NULL REFERENCES core.app_roles (code),
    created_at  timestamptz NOT NULL DEFAULT now(),
    created_by  text NOT NULL DEFAULT core.current_actor(),
    UNIQUE (model_id, username, role)        -- several roles per person per model allowed
);
CREATE INDEX model_users_username_idx ON core.model_users (username);
COMMENT ON TABLE core.model_users IS 'People''s roles on a model (D96): model-admin, architect, model-sub-admin or report-viewer';
CREATE FUNCTION core.check_model_role() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT scope FROM core.app_roles WHERE code = NEW.role) <> 'model' THEN
        RAISE EXCEPTION '% is a global role: it is given in Keycloak, not on a model', NEW.role;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER model_users_role BEFORE INSERT OR UPDATE ON core.model_users
    FOR EACH ROW EXECUTE FUNCTION core.check_model_role();

-- ---------------------------------------------------------------- ancestors (D60)
CREATE TABLE core.model_ancestors (
    model_id    bigint NOT NULL REFERENCES core.models (id),
    ancestor_id bigint NOT NULL REFERENCES core.models (id),
    PRIMARY KEY (model_id, ancestor_id)
);

-- Rebuilt whole after any change to the model tree. It must see every model, whoever made the change
-- (row-level security would otherwise hide models and lose their ancestors), so it reads with the
-- owner's bypass on for the length of the call (see core.may_read_model).
CREATE FUNCTION core.refresh_model_ancestors() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_before text := coalesce(current_setting('eax.rls_bypass', true), '');
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    DELETE FROM core.model_ancestors;
    INSERT INTO core.model_ancestors (model_id, ancestor_id)
    WITH RECURSIVE up (model_id, ancestor_id) AS (
        SELECT id, a FROM core.models, unnest(ARRAY[parent_model_id, source_model_id]) a WHERE a IS NOT NULL
        UNION
        SELECT up.model_id, a FROM up JOIN core.models m ON m.id = up.ancestor_id,
               unnest(ARRAY[m.parent_model_id, m.source_model_id]) a
         WHERE a IS NOT NULL AND a <> up.model_id
    )
    SELECT DISTINCT model_id, ancestor_id FROM up;
    PERFORM set_config('eax.rls_bypass', v_before, true);
    RETURN NULL;
END;
$$;
CREATE TRIGGER models_ancestors AFTER INSERT OR UPDATE OF parent_model_id, source_model_id OR DELETE ON core.models
    FOR EACH STATEMENT EXECUTE FUNCTION core.refresh_model_ancestors();
-- fill it once for the models already there
INSERT INTO core.model_ancestors (model_id, ancestor_id)
WITH RECURSIVE up (model_id, ancestor_id) AS (
    SELECT id, a FROM core.models, unnest(ARRAY[parent_model_id, source_model_id]) a WHERE a IS NOT NULL
    UNION
    SELECT up.model_id, a FROM up JOIN core.models m ON m.id = up.ancestor_id,
           unnest(ARRAY[m.parent_model_id, m.source_model_id]) a
     WHERE a IS NOT NULL AND a <> up.model_id
)
SELECT DISTINCT model_id, ancestor_id FROM up;

-- Every model role with the model's name, for the Users page. eax.rls_bypass is set only while this
-- function runs, and only the tables' owner (the API's login) gets anything from it (core.may_read_model).
CREATE FUNCTION core.assignments() RETURNS TABLE (username text, model_guid uuid, model_name text, model_kind text, role text)
LANGUAGE plpgsql VOLATILE AS $$
DECLARE
    v_before text := coalesce(current_setting('eax.rls_bypass', true), '');
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY SELECT u.username, m.guid, m.name, m.kind_code, u.role
                   FROM core.model_users u JOIN core.models m ON m.id = u.model_id ORDER BY m.name;
    PERFORM set_config('eax.rls_bypass', v_before, true);   -- the rows are read: back to normal at once
END;
$$;

-- ---------------------------------------------------------------- what a user may read and change
-- The current user's roles on a model (empty: none). SECURITY DEFINER: model_users has no row-level
-- security, so this works from any login reading through a policy.
CREATE FUNCTION core.model_roles(p_model bigint) RETURNS text[] LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, core AS $$
    SELECT coalesce(array_agg(role), ARRAY[]::text[]) FROM core.model_users
     WHERE model_id = p_model AND username = lower(core.current_actor())
$$;

-- The models the current user may read: those where they have a role, and their ancestors (NULL: every model)
CREATE FUNCTION core.readable_models() RETURNS bigint[] LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, core AS $$
    SELECT CASE WHEN core.sees_every_model() THEN NULL ELSE coalesce((
        SELECT array_agg(DISTINCT x) FROM (
            SELECT model_id AS x FROM core.model_users WHERE username = lower(core.current_actor())
            UNION
            SELECT a.ancestor_id FROM core.model_ancestors a
              JOIN core.model_users u ON u.model_id = a.model_id AND u.username = lower(core.current_actor())
        ) s), ARRAY[]::bigint[]) END
$$;

CREATE FUNCTION core.may_read_model(p_model bigint) RETURNS boolean LANGUAGE sql STABLE AS $$
    -- the bypass counts only for the tables' owner (the API's login): another login (reports, a
    -- person's own psql) that sets eax.rls_bypass gets nothing from it
    SELECT (current_setting('eax.rls_bypass', true) = 'on'
            AND session_user::regrole = (SELECT relowner::regrole FROM pg_class WHERE oid = 'core.models'::regclass))
        OR core.sees_every_model()
        OR p_model = ANY (core.readable_models())
$$;

-- The library (templates and reference models) is open to everyone signed in (D98): they are what
-- models are created from, and they are read only. (Used by the policies on content tables; the policy
-- on core.models looks at the row's own kind, so it never queries itself.)
CREATE FUNCTION core.is_library_model(p_model bigint) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT coalesce((SELECT kind_code IN ('template', 'reference') FROM core.models WHERE id = p_model), false)
$$;

-- The placeholder from phase 1 (always true) now asks the real question; eax.get_entity and the
-- repository's searches use it
CREATE OR REPLACE FUNCTION core.can_read_model(p_model bigint) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT core.may_read_model(p_model) OR core.is_library_model(p_model)
$$;

-- Who may change what (NULL: allowed; else why not). Parts:
--   metamodel  the metamodel tables and versions: the model's Model Admin
--   content    entities, relationships, values: the model's Model Admin, Architect or Model Sub Admin
--   model      the model row (locks, properties): its Model Admin
--   people     roles on the model: its Model Admin
--   create     a new model: Model Creators; a Model Admin for a model derived from theirs. Whoever
--              creates a model becomes its Model Admin (core.creator_becomes_model_admin).
-- Super Admins may do everything. Ancestors are read only: a role on a child gives none on its parents.
CREATE FUNCTION core.why_not(p_model bigint, p_part text) RETURNS text LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, core AS $$
DECLARE
    r    text[] := core.session_roles();
    mine text[];
BEGIN
    IF r IS NULL OR core.is_installer() OR 'super-admin' = ANY (r) THEN
        RETURN NULL;
    END IF;
    IF p_part = 'create' AND 'model-creator' = ANY (r) THEN
        RETURN NULL;
    END IF;
    mine := CASE WHEN p_model IS NULL THEN ARRAY[]::text[] ELSE core.model_roles(p_model) END;
    IF 'model-admin' = ANY (mine) AND p_part IN ('metamodel', 'content', 'model', 'people', 'create') THEN
        RETURN NULL;
    END IF;
    IF mine && ARRAY['architect', 'model-sub-admin'] AND p_part = 'content' THEN
        RETURN NULL;
    END IF;
    RETURN CASE
        WHEN p_part = 'create' THEN 'creating a model needs the Model Creator role, or Model Admin on the model it comes from'
        WHEN cardinality(mine) = 0 THEN 'you have no role on this model (its Model Admin gives roles on its People tab)'
        WHEN p_part = 'content' THEN 'changing content needs the Architect, Model Sub Admin or Model Admin role on this model'
        WHEN p_part = 'people' THEN 'giving people roles on this model needs its Model Admin role'
        ELSE 'this needs the Model Admin role on this model' END;
END;
$$;

CREATE FUNCTION core.refuse_unpermitted() RETURNS trigger LANGUAGE plpgsql AS $$
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
        IF TG_OP = 'INSERT' THEN
            -- a new model: judged on the model it comes from (Model Admins may derive from theirs)
            v_part := 'create';
            v_model := coalesce(NEW.parent_model_id, NEW.source_model_id);
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

-- True when the current user created the model and nobody has a role on it yet
CREATE FUNCTION core.first_role_by_creator(p_model bigint) RETURNS boolean LANGUAGE plpgsql VOLATILE AS $$
DECLARE
    v_before text := coalesce(current_setting('eax.rls_bypass', true), '');
    v_ok     boolean;
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    v_ok := EXISTS (SELECT 1 FROM core.models WHERE id = p_model AND created_by = core.current_actor())
            AND NOT EXISTS (SELECT 1 FROM core.model_users WHERE model_id = p_model);
    PERFORM set_config('eax.rls_bypass', v_before, true);
    RETURN v_ok;
END;
$$;

-- Whoever creates a model (a signed-in person) becomes its Model Admin; roles on the model it comes
-- from are not copied (D97)
CREATE FUNCTION core.creator_becomes_model_admin() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF core.session_roles() IS NOT NULL THEN
        INSERT INTO core.model_users (model_id, username, role) VALUES (NEW.id, lower(core.current_actor()), 'model-admin');
    END IF;
    RETURN NULL;
END;
$$;
CREATE TRIGGER models_creator_role AFTER INSERT ON core.models
    FOR EACH ROW EXECUTE FUNCTION core.creator_becomes_model_admin();

DO $$
DECLARE
    t text;
BEGIN
    -- '_00_' runs before the lock triggers ('_0_', '_1_'), so a refusal names the real reason
    FOREACH t IN ARRAY ARRAY['layers', 'entity_types', 'relationship_types', 'pick_lists', 'pick_list_values',
                             'attribute_types', 'item_attributes', 'validation_rules', 'allowed_relationships',
                             'metamodel_versions'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON core.%I
                        FOR EACH ROW EXECUTE FUNCTION core.refuse_unpermitted(''metamodel'')', t || '_00_access', t);
    END LOOP;
    FOREACH t IN ARRAY ARRAY['entities', 'relationships', 'attribute_values', 'display_id_counters'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON core.%I
                        FOR EACH ROW EXECUTE FUNCTION core.refuse_unpermitted(''content'')', t || '_00_access', t);
    END LOOP;
END;
$$;
CREATE TRIGGER models_00_access BEFORE INSERT OR UPDATE OR DELETE ON core.models
    FOR EACH ROW EXECUTE FUNCTION core.refuse_unpermitted('model');
CREATE TRIGGER model_users_00_access BEFORE INSERT OR UPDATE OR DELETE ON core.model_users
    FOR EACH ROW EXECUTE FUNCTION core.refuse_unpermitted('people');

-- Role mappings: Super Admins and User Admins only
CREATE FUNCTION core.refuse_role_mapping_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF core.session_roles() IS NOT NULL AND NOT core.session_roles() && ARRAY['super-admin', 'user-admin'] THEN
        RAISE EXCEPTION 'Not allowed for %: mapping Keycloak roles needs the User Admin or Super Admin role', core.current_actor()
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER role_mappings_00_access BEFORE INSERT OR UPDATE OR DELETE ON core.role_mappings
    FOR EACH ROW EXECUTE FUNCTION core.refuse_role_mapping_change();

-- ---------------------------------------------------------------- row-level security for reading
-- FORCE: the API's login owns the tables, and owners are otherwise exempt. Writes are decided by
-- the triggers above (with a clear message), so the write policies let every row through.
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['entities', 'relationships', 'attribute_values'] LOOP
        EXECUTE format('ALTER TABLE core.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE core.%I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('CREATE POLICY read_by_model ON core.%I FOR SELECT
                        USING (core.may_read_model(model_id) OR core.is_library_model(model_id))', t);
        EXECUTE format('CREATE POLICY add ON core.%I FOR INSERT WITH CHECK (true)', t);
        EXECUTE format('CREATE POLICY change ON core.%I FOR UPDATE USING (true) WITH CHECK (true)', t);
        EXECUTE format('CREATE POLICY remove ON core.%I FOR DELETE USING (true)', t);
    END LOOP;
END;
$$;
ALTER TABLE core.models ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.models FORCE ROW LEVEL SECURITY;
CREATE POLICY read_by_model ON core.models FOR SELECT USING (kind_code IN ('template', 'reference') OR core.may_read_model(id));
CREATE POLICY add ON core.models FOR INSERT WITH CHECK (true);
CREATE POLICY change ON core.models FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY remove ON core.models FOR DELETE USING (true);

-- ---------------------------------------------------------------- rights for the installer
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.model_users, core.model_ancestors TO eax_migrator;
        GRANT SELECT ON core.app_roles, core.role_mappings TO eax_migrator;
    END IF;
END;
$$;
