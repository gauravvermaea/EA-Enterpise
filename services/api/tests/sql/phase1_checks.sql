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
    v_model bigint := (SELECT id FROM core.models WHERE name = 'Sample insurance model');
    v_tpl   bigint := (SELECT id FROM core.models WHERE kind_code = 'template');
    n bigint;
    t text[];
BEGIN
    -- seed shape
    ASSERT (SELECT count(*) FROM core.entity_types WHERE model_id = v_tpl) = 42, '42 ArchiMate 4 element types';
    ASSERT (SELECT count(*) FROM core.relationship_types WHERE model_id = v_tpl) = 11, '11 relationship types';
    ASSERT (SELECT count(*) FROM core.entity_types WHERE model_id = v_model AND origin_guid IS NULL) = 0,
        'every sample type points back at the template';

    -- get_entity: the caller names the tables; a used name is refused; drop_entity removes them
    t := eax.get_entity('Application Component', 'apps');
    ASSERT t = ARRAY['apps', 'apps_rel'], 'table names as given';
    ASSERT (SELECT count(*) FROM apps) = 3, 'three sample applications';
    ASSERT (SELECT data_type FROM information_schema.columns
             WHERE table_name = 'apps' AND column_name = 'go_live_date') = 'date', 'typed columns';
    ASSERT (SELECT count(*) FROM apps_rel WHERE entity_name = 'Claims Platform') = 5,
        'Claims Platform has five relationships';
    t := eax.get_entity('Application Component', 'e_' || replace(gen_random_uuid()::text, '-', ''));
    ASSERT t[1] ~ '^e_[0-9a-f]{32}$', 'guid-based name';
    t := eax.get_entity_by_name('capability', 'CLAIMS MANAGEMENT', 'cap');
    ASSERT (SELECT count(*) FROM cap) = 1, 'by name, case-insensitive';
    t := eax.get_entity('application_component', 'apps_only', NULL, false);
    ASSERT t = ARRAY['apps_only'], 'no relationships';
    PERFORM eax.drop_entity('apps');
    ASSERT to_regclass('pg_temp.apps') IS NULL AND to_regclass('pg_temp.apps_rel') IS NULL, 'drop_entity';

    -- model hierarchy: any depth; parent = merges into, source = created from
    ASSERT (SELECT parent_model_id IS NULL AND source_model_id = v_tpl FROM core.models WHERE id = v_model),
        'sample model: created from the template, top level';
    INSERT INTO core.models (name, kind_code, parent_model_id, source_model_id)
    VALUES ('Copy 1', 'project', v_model, v_model);
    INSERT INTO core.models (name, kind_code, parent_model_id, source_model_id)
    SELECT 'Copy 1.1', 'project', id, id FROM core.models WHERE name = 'Copy 1';
    INSERT INTO core.models (name, kind_code, parent_model_id, source_model_id)
    SELECT 'Copy 1.1.1', 'project', id, id FROM core.models WHERE name = 'Copy 1.1';
    ASSERT (WITH RECURSIVE up AS (
                SELECT id, parent_model_id, 0 AS depth FROM core.models WHERE name = 'Copy 1.1.1'
                UNION ALL SELECT m.id, m.parent_model_id, up.depth + 1 FROM core.models m JOIN up ON m.id = up.parent_model_id)
            SELECT max(depth) FROM up) = 3, 'three levels under the sample model';

    -- display ids and history
    INSERT INTO core.entities (model_id, entity_type_id, name)
    SELECT v_model, id, 'Check Portal' FROM core.entity_types WHERE model_id = v_model AND code = 'ApplicationComponent';
    ASSERT (SELECT display_id FROM core.entities WHERE name = 'Check Portal') = 'APP-0004', 'next display id';
    UPDATE core.entities SET description = 'changed' WHERE name = 'Check Portal';
    ASSERT (SELECT row_version FROM core.entities WHERE name = 'Check Portal') = 2, 'row_version counts updates';
    SELECT count(*) INTO n FROM history.row_versions
     WHERE row_guid = (SELECT guid FROM core.entities WHERE name = 'Check Portal');
    ASSERT n = 2, 'history keeps both versions';
END $$;

-- integrity rules
SELECT pg_temp.expect_error($q$
    INSERT INTO core.relationships (model_id, relationship_type_id, source_entity_id, target_entity_id)
    SELECT e1.model_id, rt.id, e1.id, e2.id FROM core.entities e1, core.entities e2, core.relationship_types rt
     WHERE e1.name = 'Claim Record' AND e2.name = 'Settle claims faster' AND rt.code = 'Serving' AND rt.model_id = e1.model_id
$q$, 'does not allow');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.attribute_values (model_id, attribute_type_id, entity_id, value_text)
    SELECT e.model_id, a.id, e.id, 'Sideways' FROM core.entities e
      JOIN core.attribute_types a ON a.model_id = e.model_id AND a.code = 'Maturity' WHERE e.name = 'Policy Management'
$q$, 'not in the pick list');
SELECT pg_temp.expect_error($q$
    UPDATE core.attribute_values SET value_date = NULL, value_text = 'soon'
     WHERE attribute_type_id IN (SELECT id FROM core.attribute_types WHERE code = 'GoLiveDate') AND value_date IS NOT NULL
$q$, 'holds date values');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.attribute_values (model_id, attribute_type_id, entity_id, value_text)
    SELECT e.model_id, a.id, e.id, 'SaaS' FROM core.entities e
      JOIN core.attribute_types a ON a.model_id = e.model_id AND a.code = 'Hosting' WHERE e.name = 'Settle claims faster'
$q$, 'does not apply');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.entities (model_id, entity_type_id, name)
    SELECT model_id, id, 'X' FROM core.entity_types
     WHERE code = 'Goal' AND model_id = (SELECT id FROM core.models WHERE kind_code = 'template')
$q$, 'template model holds a metamodel only');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.models (name, kind_code, parent_model_id)
    SELECT 'Under template', 'project', id FROM core.models WHERE kind_code = 'template'
$q$, 'cannot be a parent');
SELECT pg_temp.expect_error($q$
    UPDATE core.models SET parent_model_id = (SELECT id FROM core.models WHERE name = 'Copy 1.1.1')
     WHERE name = 'Copy 1'
$q$, 'make a loop');
SELECT pg_temp.expect_error($q$
    UPDATE core.models SET parent_model_id = id WHERE name = 'Copy 1'
$q$, 'its own parent');
SELECT pg_temp.expect_error($q$ DELETE FROM history.row_versions WHERE id = (SELECT min(id) FROM history.row_versions) $q$,
    'append-only');
SELECT pg_temp.expect_error($q$ SELECT eax.get_entity('Nonsense', 'x') $q$, 'No entity type');
SELECT pg_temp.expect_error($q$ SELECT eax.get_entity('Capability', NULL) $q$, 'Give a name');
SELECT pg_temp.expect_error($q$ SELECT eax.get_entity('Capability', 'Bad Name') $q$, 'must be lower-case');
SELECT pg_temp.expect_error($q$ SELECT eax.get_entity('Capability', 'cap') $q$, 'already exists');

SELECT 'phase 1 checks passed' AS result;
ROLLBACK;
