-- Phase 3 database checks: metamodel versions, metamodel versions on entities, model locks.
-- Run as postgres against a database with the phase 3 schema and seed:
--   psql -U postgres -d eaexplorer -v ON_ERROR_STOP=1 -f tests/sql/phase3_checks.sql
-- Runs in one transaction that is rolled back. Ends with "phase 3 checks passed".
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

SELECT set_config('eax.actor', 'phase3.check', true);

DO $$
DECLARE
    v_m   bigint := (SELECT id FROM core.models WHERE name = 'Sample insurance model');
    v_t   bigint;
    v_ver integer;
    v_e   bigint;
BEGIN
    ASSERT string_to_array(core.schema_version(), '.')::int[] >= ARRAY[0, 3, 0], 'database version 0.3.0 or later';
    ASSERT (SELECT count(*) FROM core.metamodel_versions WHERE version = 1) =
           (SELECT count(*) FROM core.models), 'every model has its first metamodel version';
    ASSERT NOT EXISTS (SELECT 1 FROM core.entities WHERE created_mm_version IS NULL), 'entities carry their metamodel version';

    -- publishing a version bumps the model, writes the version row and labels the history
    v_ver := core.publish_metamodel_version(v_m, 'check: new entity type');
    ASSERT v_ver = (SELECT metamodel_version FROM core.models WHERE id = v_m), 'model carries the new version';
    INSERT INTO core.entity_types (model_id, layer_id, code, name, id_prefix, table_name)
    SELECT v_m, id, 'CheckType', 'Check Type', 'CHK', 'check_type' FROM core.layers WHERE model_id = v_m LIMIT 1
    RETURNING id INTO v_t;
    ASSERT (SELECT label FROM history.row_versions WHERE table_name = 'entity_types' AND row_id = v_t)
           = 'metamodel v' || v_ver || ': check: new entity type', 'history labelled with the version';

    -- an entity records the version it was created in and last changed in
    INSERT INTO core.entities (model_id, entity_type_id, name) VALUES (v_m, v_t, 'Check entity') RETURNING id INTO v_e;
    ASSERT (SELECT created_mm_version = v_ver AND modified_mm_version = v_ver FROM core.entities WHERE id = v_e), 'versions stamped';
    PERFORM core.publish_metamodel_version(v_m, 'check: second');
    UPDATE core.entities SET description = 'changed' WHERE id = v_e;
    ASSERT (SELECT created_mm_version = v_ver AND modified_mm_version = v_ver + 1 FROM core.entities WHERE id = v_e),
        'last changed in the newer version, created version kept';
END $$;

-- metamodel lock: metamodel refused, content allowed
UPDATE core.models SET lock_level = 'metamodel', lock_reason = 'check' WHERE name = 'Sample insurance model';
SELECT pg_temp.expect_error($q$
    UPDATE core.entity_types SET description = 'x' WHERE code = 'CheckType'
$q$, 'is locked');
SELECT pg_temp.expect_error($q$
    SELECT core.publish_metamodel_version((SELECT id FROM core.models WHERE name = 'Sample insurance model'), 'x')
$q$, 'is locked');
UPDATE core.entities SET description = 'content still editable' WHERE name = 'Check entity';
SELECT pg_temp.expect_error($q$
    UPDATE core.models SET lock_level = 'content' WHERE name = 'Sample insurance model'
$q$, 'already locked');

-- metamodel and content lock: both refused
UPDATE core.models SET lock_level = 'none' WHERE name = 'Sample insurance model';
UPDATE core.models SET lock_level = 'content' WHERE name = 'Sample insurance model';
SELECT pg_temp.expect_error($q$ UPDATE core.entities SET description = 'x' WHERE name = 'Check entity' $q$, 'nothing can be changed');
SELECT pg_temp.expect_error($q$ UPDATE core.entity_types SET description = 'x' WHERE code = 'CheckType' $q$, 'nothing can be changed');

-- maintenance lock: the person who set it may change, others may not
UPDATE core.models SET lock_level = 'none' WHERE name = 'Sample insurance model';
UPDATE core.models SET lock_level = 'maintenance', lock_reason = 'merge' WHERE name = 'Sample insurance model';
DO $$
BEGIN
    ASSERT (SELECT locked_by FROM core.models WHERE name = 'Sample insurance model') = 'phase3.check', 'locked_by stamped';
END $$;
UPDATE core.entities SET description = 'by the maintainer' WHERE name = 'Check entity';
SELECT set_config('eax.actor', 'someone.else', true);
SELECT pg_temp.expect_error($q$ UPDATE core.entities SET description = 'x' WHERE name = 'Check entity' $q$, 'under maintenance');
SELECT set_config('eax.actor', 'phase3.check', true);
UPDATE core.models SET lock_level = 'none' WHERE name = 'Sample insurance model';
DO $$
BEGIN
    ASSERT (SELECT locked_by IS NULL AND lock_reason = '' FROM core.models WHERE name = 'Sample insurance model'), 'unlock clears';
END $$;

-- the installer's lock on reference models is unchanged and cannot be replaced by a model lock
SELECT pg_temp.expect_error($q$
    UPDATE core.models SET lock_level = 'none', lock_reason = 'x' WHERE name = 'Insurance reference model'
$q$, 'is locked');

SELECT 'phase 3 checks passed' AS result;
ROLLBACK;
