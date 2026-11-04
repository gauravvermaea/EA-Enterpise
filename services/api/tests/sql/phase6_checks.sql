-- Phase 6 database checks: data entry by people with content roles, tags, rule overrides (D48) and
-- relationships outside the metamodel (D49). Run as the API's login, with the laptop sample loaded:
--   Get-Content services/api/tests/sql/phase6_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
-- Runs in one transaction that is rolled back. Ends with "phase 6 checks passed".
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
CREATE FUNCTION pg_temp.as_user(p_user text, p_roles text) RETURNS void LANGUAGE sql AS $$
    SELECT set_config('eax.actor', p_user, true), set_config('eax.user_roles', p_roles, true)
$$;

DO $$
DECLARE
    v_model bigint;
    v_app   bigint;
    v_cap   bigint;
    v_rel   bigint;
    v_e     bigint;
    v_tags  text[];
    v_n     integer;
    v_ver   integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM core.schema_versions WHERE version = '0.6.0') THEN
        RAISE EXCEPTION 'schema version 0.6.0 (0010_data_entry) is missing';
    END IF;
    PERFORM set_config('eax.rls_bypass', 'on', true);
    SELECT id INTO v_model FROM core.models WHERE name = 'Sample insurance model' AND NOT is_deleted;
    SELECT id INTO v_app FROM core.entity_types WHERE model_id = v_model AND code = 'ApplicationComponent';
    SELECT id INTO v_cap FROM core.entity_types WHERE model_id = v_model AND code = 'Capability';
    SELECT id INTO v_rel FROM core.relationship_types WHERE model_id = v_model AND code = 'Serving';
    IF v_model IS NULL OR v_app IS NULL OR v_cap IS NULL OR v_rel IS NULL THEN
        RAISE EXCEPTION 'the sample model and its ArchiMate types are missing (load the sample)';
    END IF;
    PERFORM set_config('eax.rls_bypass', '', true);

    -- an Architect on the model enters an entity with tags (cleaned: lower case, no duplicates, sorted)
    PERFORM pg_temp.as_user('user_architect', 'user');
    INSERT INTO core.entities (model_id, entity_type_id, name, tags)
    VALUES (v_model, v_app, 'Phase 6 check app', ARRAY[' Cloud', 'critical', 'cloud', ''])
    RETURNING id, tags INTO v_e, v_tags;
    IF v_tags <> ARRAY['cloud', 'critical'] THEN
        RAISE EXCEPTION 'tags were not cleaned: %', v_tags;
    END IF;
    IF (SELECT display_id FROM core.entities WHERE id = v_e) NOT LIKE '%-%' THEN
        RAISE EXCEPTION 'a new entity got no display ID';
    END IF;

    -- a value saved although it fails a rule keeps the override details (D48)
    INSERT INTO core.attribute_values (model_id, attribute_type_id, entity_id, value_number, rule_override)
    SELECT v_model, id, v_e, 9, '{"rules": [{"rule": "range"}], "by": "user_architect"}'::jsonb
      FROM core.attribute_types WHERE model_id = v_model AND code = 'Criticality';
    IF NOT EXISTS (SELECT 1 FROM core.attribute_values WHERE entity_id = v_e AND rule_override IS NOT NULL) THEN
        RAISE EXCEPTION 'the rule override was not kept';
    END IF;

    -- a Report Viewer may not change content
    PERFORM pg_temp.as_user('user_report_viewer', 'user');
    PERFORM pg_temp.expect_error(format('UPDATE core.entities SET name = %L WHERE id = %s', 'x', v_e), 'Not allowed');
    PERFORM pg_temp.expect_error(format('SELECT core.allow_from_content(%s, %s, %s, %s)', v_model, v_rel, v_app, v_app), 'Not allowed');

    -- an Architect adds a relationship the metamodel does not allow: the mapping is added, flagged (D49)
    PERFORM pg_temp.as_user('user_architect', 'user');
    PERFORM pg_temp.expect_error(format('INSERT INTO core.allowed_relationships (model_id, relationship_type_id, source_type_id, target_type_id) VALUES (%s, %s, %s, %s)',
                                        v_model, v_rel, v_cap, v_cap), 'Not allowed');
    v_ver := core.allow_from_content(v_model, v_rel, v_cap, v_cap);
    IF NOT EXISTS (SELECT 1 FROM core.allowed_relationships WHERE relationship_type_id = v_rel AND source_type_id = v_cap
                     AND target_type_id = v_cap AND from_content AND NOT is_deleted) THEN
        RAISE EXCEPTION 'allow_from_content did not add the flagged mapping';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM core.metamodel_versions WHERE model_id = v_model AND version = v_ver) THEN
        RAISE EXCEPTION 'allow_from_content did not make a metamodel version';
    END IF;
    IF core.session_roles() IS DISTINCT FROM ARRAY['user'] THEN
        RAISE EXCEPTION 'allow_from_content did not give back the person''s roles';
    END IF;

    -- retire and delete are kept in history
    UPDATE core.entities SET status_code = 'retired' WHERE id = v_e;
    UPDATE core.entities SET is_deleted = true WHERE id = v_e;
    SELECT count(*) INTO v_n FROM history.row_versions WHERE table_name = 'entities' AND row_id = v_e;
    IF v_n < 3 THEN
        RAISE EXCEPTION 'the entity''s history has % versions, expected at least 3', v_n;
    END IF;

    -- tags reach the reports
    IF to_regclass('rpt.entity_tags') IS NULL THEN
        RAISE EXCEPTION 'rpt.entity_tags is missing';
    END IF;
END $$;

SELECT 'phase 6 checks passed' AS result;
ROLLBACK;
