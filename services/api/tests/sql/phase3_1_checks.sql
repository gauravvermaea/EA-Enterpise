-- Phase 3.1 database checks: global roles (from Keycloak) and roles per model, enforced by the database.
-- Run as the API's login (it owns the tables, so row-level security applies to it; a superuser
-- would bypass it):
--   psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1 -f tests/sql/phase3_1_checks.sql
-- Runs in one transaction that is rolled back. Ends with "phase 3.1 checks passed".
BEGIN;

CREATE FUNCTION pg_temp.expect_error(p_sql text, p_fragment text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE p_sql;
    EXCEPTION WHEN OTHERS THEN
        IF position(p_fragment IN SQLERRM) = 0 THEN
            RAISE EXCEPTION 'expected an error containing "%", got: %', p_fragment, SQLERRM;
        END IF;
        RETURN;
    END;
    RAISE EXCEPTION 'expected an error containing "%", but the statement succeeded', p_fragment;
END $$;

-- who is asking, as the API sets it: the user and their global roles
CREATE FUNCTION pg_temp.as_user(p_user text, p_roles text) RETURNS void LANGUAGE sql AS $$
    SELECT set_config('eax.actor', p_user, true), set_config('eax.user_roles', p_roles, true)
$$;
CREATE FUNCTION pg_temp.nobody() RETURNS void LANGUAGE sql AS $$
    SELECT set_config('eax.actor', '', true), set_config('eax.user_roles', '', true)
$$;
-- working models seen (the library, templates and reference models, is open to everyone signed in: D98)
CREATE FUNCTION pg_temp.models_seen() RETURNS bigint LANGUAGE sql AS $$
    SELECT count(*) FROM core.models WHERE kind_code NOT IN ('template', 'reference')
$$;
CREATE FUNCTION pg_temp.m(p_name text) RETURNS bigint LANGUAGE sql AS $$
    SELECT id FROM core.models WHERE name = p_name
$$;

-- one person, roles on two models, two of them on one (set up with no user set: the installer's way)
INSERT INTO core.model_users (model_id, username, role) VALUES
    ((SELECT id FROM core.models WHERE name = 'Sample insurance model'), 'check_person', 'architect'),
    ((SELECT id FROM core.models WHERE name = 'Sample insurance model'), 'check_person', 'report-viewer'),
    ((SELECT id FROM core.models WHERE name = 'Insurance reference model'), 'check_person', 'report-viewer'),
    ((SELECT id FROM core.models WHERE name = 'Sample insurance model'), 'check_admin', 'model-admin');

DO $$
DECLARE
    v_all bigint := (SELECT count(*) FROM core.models WHERE kind_code NOT IN ('template', 'reference'));
BEGIN
    ASSERT string_to_array(core.schema_version(), '.')::int[] >= ARRAY[0, 3, 1], 'database version 0.3.1 or later';
    ASSERT (SELECT count(*) FROM core.app_roles WHERE scope = 'global') >= 6, 'six global roles (seven from 0.4.0: Library Admin)';
    ASSERT (SELECT count(*) FROM core.app_roles WHERE scope = 'model') = 4, 'four model roles';
    ASSERT (SELECT app_role FROM core.role_mappings WHERE keycloak_role = 'eax-user') = 'user', 'default mapping';
    ASSERT (SELECT count(*) FROM core.model_ancestors WHERE model_id = pg_temp.m('Sample insurance model')) >= 1,
        'the sample model has its template as an ancestor';

    -- a User with no model role sees nothing
    PERFORM pg_temp.as_user('check_nobody', 'user');
    ASSERT pg_temp.models_seen() = 0, 'a User with no model role sees no model';
    ASSERT (SELECT count(*) FROM core.entities e JOIN core.models m ON m.id = e.model_id WHERE m.kind_code = 'project') = 0,
        'nor any entity of a working model';
    ASSERT EXISTS (SELECT 1 FROM core.models WHERE kind_code = 'reference'), 'but the library is open';
    ASSERT (SELECT count(*) FROM core.entities e JOIN core.models m ON m.id = e.model_id WHERE m.kind_code = 'reference') > 0,
        'with its content';

    -- a person sees the models where they have a role, and their ancestors
    PERFORM pg_temp.as_user('check_person', 'user');
    ASSERT EXISTS (SELECT 1 FROM core.models WHERE name = 'Sample insurance model'), 'Architect there';
    ASSERT EXISTS (SELECT 1 FROM core.models WHERE name = 'Insurance reference model'), 'Report Viewer there';
    ASSERT EXISTS (SELECT 1 FROM core.models WHERE name = 'ArchiMate 4'), 'and the template both come from';
    ASSERT NOT EXISTS (SELECT 1 FROM core.models WHERE name = 'Fynbos Life'), 'but no other model';

    ASSERT core.model_roles(pg_temp.m('Sample insurance model')) @> ARRAY['architect', 'report-viewer'], 'two roles on one model';

    -- only Super Admins read every model; a Model Creator, a User Admin and an IT Admin read none of their own
    PERFORM pg_temp.as_user('check_super', 'super-admin');
    ASSERT pg_temp.models_seen() = v_all, 'Super Admin: every model';
    PERFORM pg_temp.as_user('check_creator', 'model-creator,user');
    ASSERT pg_temp.models_seen() = 0, 'Model Creator: only models they have a role on';
    PERFORM pg_temp.as_user('check_ua', 'user-admin');
    ASSERT pg_temp.models_seen() = 0, 'User Admin: no model content';
    PERFORM pg_temp.as_user('check_it', 'it-admin');
    ASSERT pg_temp.models_seen() = 0, 'IT Admin: no model content';
END $$;

-- the same person: content changes where they are Architect, nothing where they are Report Viewer
SELECT pg_temp.as_user('check_person', 'user');
UPDATE core.entities SET description = 'changed by its Architect'
 WHERE model_id = pg_temp.m('Sample insurance model') AND name = 'Claims Platform';
SELECT pg_temp.expect_error($q$
    UPDATE core.entities SET description = 'x' WHERE model_id = pg_temp.m('Insurance reference model')
$q$, 'needs the Architect, Model Sub Admin or Model Admin role on this model');
SELECT pg_temp.expect_error($q$
    UPDATE core.entity_types SET description = 'x' WHERE model_id = pg_temp.m('Sample insurance model') AND code = 'ApplicationComponent'
$q$, 'needs the Model Admin role on this model');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.model_users (model_id, username, role) VALUES (pg_temp.m('Sample insurance model'), 'someone', 'architect')
$q$, 'giving people roles on this model');
SELECT pg_temp.expect_error($q$
    UPDATE core.models SET lock_level = 'metamodel' WHERE id = pg_temp.m('Sample insurance model')
$q$, 'needs the Model Admin role on this model');
-- ancestors are read only
SELECT pg_temp.expect_error($q$
    UPDATE core.entity_types SET description = 'x' WHERE model_id = (SELECT id FROM core.models WHERE name = 'ArchiMate 4')
$q$, 'Not allowed');

-- the model's Model Admin: metamodel, lock, people (on this model only)
SELECT pg_temp.as_user('check_admin', 'user');
UPDATE core.entity_types SET description = 'changed by its Model Admin'
 WHERE model_id = pg_temp.m('Sample insurance model') AND code = 'ApplicationComponent';
UPDATE core.models SET lock_level = 'metamodel' WHERE id = pg_temp.m('Sample insurance model');
UPDATE core.models SET lock_level = 'none' WHERE id = pg_temp.m('Sample insurance model');
INSERT INTO core.model_users (model_id, username, role) VALUES (pg_temp.m('Sample insurance model'), 'check_new', 'report-viewer');
INSERT INTO core.model_users (model_id, username, role) VALUES (pg_temp.m('Sample insurance model'), 'check_new', 'architect');
DELETE FROM core.model_users WHERE username = 'check_new' AND role = 'report-viewer';
SELECT pg_temp.expect_error($q$
    INSERT INTO core.model_users (model_id, username, role) VALUES (pg_temp.m('Sample insurance model'), 'check_x', 'super-admin')
$q$, 'is a global role');

-- a Model Admin of one model gives no roles on another; User Admins give no model roles
SELECT pg_temp.expect_error($q$
    INSERT INTO core.model_users (model_id, username, role) VALUES (pg_temp.m('Fynbos Life'), 'check_new', 'model-admin')
$q$, 'Not allowed');
SELECT pg_temp.as_user('check_ua', 'user-admin');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.model_users (model_id, username, role) VALUES (pg_temp.m('Sample insurance model'), 'check_new2', 'architect')
$q$, 'Not allowed');

-- a Model Creator creates a model and becomes its Model Admin (D96); a plain User may not create
SELECT pg_temp.as_user('check_creator', 'model-creator,user');
INSERT INTO core.models (name, kind_code, source_model_id, metamodel_name)
VALUES ('Check created', 'project', (SELECT id FROM core.models WHERE name = 'ArchiMate 4'), 'ArchiMate 4');
DO $$ BEGIN
    ASSERT core.model_roles(pg_temp.m('Check created')) = ARRAY['model-admin'], 'the creator is its Model Admin';
    ASSERT pg_temp.models_seen() = 1, 'and reads it (with the library it comes from)';
    PERFORM pg_temp.nobody();
    ASSERT (SELECT count(*) FROM core.model_ancestors WHERE model_id = pg_temp.m('Fynbos Life')) >= 3,
        'creating a model keeps every other model''s ancestors';
    PERFORM pg_temp.as_user('check_creator', 'model-creator,user');
END $$;
UPDATE core.models SET lock_level = 'metamodel' WHERE id = pg_temp.m('Check created');
UPDATE core.models SET lock_level = 'none' WHERE id = pg_temp.m('Check created');
SELECT pg_temp.as_user('check_nobody', 'user');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.models (name, kind_code, metamodel_name) VALUES ('Check refused', 'project', 'ArchiMate 4')
$q$, 'creating a model needs');

-- a Model Admin derives a model from theirs and becomes its Model Admin; not from someone else's
SELECT pg_temp.as_user('check_admin', 'user');
INSERT INTO core.models (name, kind_code, source_model_id, parent_model_id, metamodel_name)
VALUES ('Check derived', 'project', pg_temp.m('Sample insurance model'), pg_temp.m('Sample insurance model'), 'ArchiMate 4');
DO $$ BEGIN
    ASSERT core.model_roles(pg_temp.m('Check derived')) = ARRAY['model-admin'], 'the creator is its Model Admin';
    ASSERT NOT EXISTS (SELECT 1 FROM core.model_users WHERE model_id = pg_temp.m('Check derived') AND username = 'check_person'),
        'roles on the model it comes from are not copied';
END $$;
SELECT pg_temp.expect_error($q$
    INSERT INTO core.models (name, kind_code, source_model_id, metamodel_name)
    VALUES ('Check not mine', 'project', (SELECT id FROM core.models WHERE name = 'ArchiMate 4'), 'ArchiMate 4')
$q$, 'creating a model needs');

-- Keycloak roles map only to global roles; only User Admins and Super Admins change the mapping
SELECT pg_temp.expect_error($q$
    INSERT INTO core.role_mappings (keycloak_role, app_role) VALUES ('EA Architects', 'user')
$q$, 'needs the User Admin or Super Admin role');
SELECT pg_temp.as_user('check_ua', 'user-admin');
INSERT INTO core.role_mappings (keycloak_role, app_role) VALUES ('EA Model Owners', 'model-creator');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.role_mappings (keycloak_role, app_role) VALUES ('EA Architects', 'architect')
$q$, 'is a model role');

-- a signed-in person with no global role (the API sends "none"): only their model roles count
SELECT pg_temp.as_user('check_stranger', 'none');
DO $$ BEGIN ASSERT pg_temp.models_seen() = 0, 'no role anywhere: no model'; END $$;
SELECT pg_temp.expect_error($q$ UPDATE core.entities SET description = 'x' WHERE true $q$, 'Not allowed');

-- the Users page's list of model roles is complete for anyone the API lets call it; the bypass ends with the call
SELECT pg_temp.as_user('check_it', 'it-admin');
DO $$ BEGIN
    ASSERT (SELECT count(*) FROM core.assignments()) > 0, 'every model role listed';
    ASSERT pg_temp.models_seen() = 0, 'the bypass ends with the call';
END $$;

-- no user set (installer, seed, jobs, an administrator's psql): not restricted
SELECT pg_temp.nobody();
DO $$ BEGIN ASSERT pg_temp.models_seen() >= 3, 'with no user set, every model'; END $$;

-- rules about relationships (D113, 0007): the rule type exists; it goes only on the built-in field relationships
DO $$ BEGIN
    ASSERT EXISTS (SELECT 1 FROM core.rule_types WHERE code = 'has_relationship'), 'has_relationship rule type';
    ASSERT (SELECT count(*) FROM core.validation_rules vr JOIN core.models m ON m.id = vr.model_id
             WHERE m.name = 'Karoo Re (independent)' AND vr.rule_type_code = 'has_relationship') = 4,
        'laptop rules demo: four relationship rules in Karoo Re';
END $$;
SELECT pg_temp.expect_error($q$
    INSERT INTO core.validation_rules (model_id, field_name, rule_type_code, message)
    SELECT id, 'name', 'has_relationship', 'x' FROM core.models WHERE name = 'Karoo Re (independent)' $q$,
    'validation_rules_relationship_rule');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.validation_rules (model_id, field_name, rule_type_code, message)
    SELECT id, 'relationships', 'mandatory', 'x' FROM core.models WHERE name = 'Karoo Re (independent)' $q$,
    'validation_rules_relationship_rule');

SELECT 'phase 3.1 checks passed' AS result;
ROLLBACK;
