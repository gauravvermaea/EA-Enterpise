-- Phase 1 database checks. Run against a database that has the phase 1 schema and seed:
--   psql -v ON_ERROR_STOP=1 -f tests/sql/phase1_checks.sql
-- Each check raises an exception when it fails; the script ends with "phase 1 checks passed".
-- Everything runs in one transaction that is rolled back, so the database is left unchanged.
BEGIN;
SET LOCAL client_min_messages = warning;

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

DO $$
DECLARE
    v_model bigint := (SELECT id FROM core.model WHERE name = 'Sample insurance model');
    v_tpl   bigint := (SELECT id FROM core.model WHERE kind_code = 'template');
    n bigint;
    t text[];
BEGIN
    -- seed shape
    ASSERT (SELECT count(*) FROM core.entity_type WHERE model_id = v_tpl) = 42, '42 ArchiMate 4 element types';
    ASSERT (SELECT count(*) FROM core.relationship_type WHERE model_id = v_tpl) = 11, '11 relationship types';
    ASSERT (SELECT count(*) FROM core.entity_type WHERE model_id = v_model AND origin_guid IS NULL) = 0,
        'every sample type points back at the template';

    -- get_entity
    t := eax.get_entity('Application Component');
    ASSERT t = ARRAY['tmp_application_component', 'tmp_application_component_rel'], 'table names';
    ASSERT (SELECT count(*) FROM tmp_application_component) = 3, 'three sample applications';
    ASSERT (SELECT data_type FROM information_schema.columns
             WHERE table_name = 'tmp_application_component' AND column_name = 'go_live_date') = 'date', 'typed columns';
    ASSERT (SELECT count(*) FROM tmp_application_component_rel WHERE entity_name = 'Claims Platform') = 5,
        'Claims Platform has five relationships';
    t := eax.get_entity_by_name('capability', 'CLAIMS MANAGEMENT');
    ASSERT (SELECT count(*) FROM tmp_capability) = 1, 'by name, case-insensitive';
    t := eax.get_entity('application_component', NULL, false, 'apps');
    ASSERT t = ARRAY['tmp_apps'], 'custom table name, no relationships';

    -- display ids and history
    INSERT INTO core.entity (model_id, entity_type_id, name)
    SELECT v_model, id, 'Check Portal' FROM core.entity_type WHERE model_id = v_model AND code = 'ApplicationComponent';
    ASSERT (SELECT display_id FROM core.entity WHERE name = 'Check Portal') = 'APP-0004', 'next display id';
    UPDATE core.entity SET description = 'changed' WHERE name = 'Check Portal';
    ASSERT (SELECT row_version FROM core.entity WHERE name = 'Check Portal') = 2, 'row_version counts updates';
    SELECT count(*) INTO n FROM history.row_versions
     WHERE row_guid = (SELECT guid FROM core.entity WHERE name = 'Check Portal');
    ASSERT n = 2, 'history keeps both versions';
END $$;

-- integrity rules
SELECT pg_temp.expect_error($q$
    INSERT INTO core.relationship (model_id, relationship_type_id, source_entity_id, target_entity_id)
    SELECT e1.model_id, rt.id, e1.id, e2.id FROM core.entity e1, core.entity e2, core.relationship_type rt
     WHERE e1.name = 'Claim Record' AND e2.name = 'Settle claims faster' AND rt.code = 'Serving' AND rt.model_id = e1.model_id
$q$, 'does not allow');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.attribute_value (model_id, attribute_type_id, entity_id, value_text)
    SELECT e.model_id, a.id, e.id, 'Sideways' FROM core.entity e
      JOIN core.attribute_type a ON a.model_id = e.model_id AND a.code = 'Maturity' WHERE e.name = 'Policy Management'
$q$, 'not in the pick list');
SELECT pg_temp.expect_error($q$
    UPDATE core.attribute_value SET value_date = NULL, value_text = 'soon'
     WHERE attribute_type_id IN (SELECT id FROM core.attribute_type WHERE code = 'GoLiveDate') AND value_date IS NOT NULL
$q$, 'holds date values');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.attribute_value (model_id, attribute_type_id, entity_id, value_text)
    SELECT e.model_id, a.id, e.id, 'SaaS' FROM core.entity e
      JOIN core.attribute_type a ON a.model_id = e.model_id AND a.code = 'Hosting' WHERE e.name = 'Settle claims faster'
$q$, 'does not apply');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.entity (model_id, entity_type_id, name)
    SELECT model_id, id, 'X' FROM core.entity_type
     WHERE code = 'Goal' AND model_id = (SELECT id FROM core.model WHERE kind_code = 'template')
$q$, 'template model holds a metamodel only');
SELECT pg_temp.expect_error($q$ DELETE FROM history.row_versions WHERE id = (SELECT min(id) FROM history.row_versions) $q$,
    'append-only');
SELECT pg_temp.expect_error($q$ SELECT eax.get_entity('Nonsense') $q$, 'No entity type');

SELECT 'phase 1 checks passed' AS result;
ROLLBACK;
