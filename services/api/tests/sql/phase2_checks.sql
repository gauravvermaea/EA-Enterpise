-- Phase 2 database checks: schema version, model properties, the insurance reference model and
-- the lock on reference models. Run as an administrator (for example postgres) against a database
-- with the phase 2 schema and seed:
--   psql -U postgres -d eaexplorer -v ON_ERROR_STOP=1 -f tests/sql/phase2_checks.sql
-- Every change below must be refused, the superuser included. Ends with "phase 2 checks passed";
-- runs in one transaction that is rolled back. phase2_installer_check.sql proves the other side:
-- the installer's login may change a locked model.
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
    v_ins bigint := (SELECT id FROM core.models WHERE name = 'Insurance reference model');
BEGIN
    -- version
    ASSERT string_to_array(core.schema_version(), '.')::int[] >= ARRAY[0, 2, 0], 'database version 0.2.0 or later';
    ASSERT (SELECT count(*) FROM core.schema_versions WHERE version IN ('0.1.0', '0.2.0')) = 2, 'versions 0.1.0 and 0.2.0 recorded';

    -- the insurance reference model
    ASSERT v_ins IS NOT NULL, 'insurance reference model loaded';
    ASSERT (SELECT is_locked AND kind_code = 'reference' AND industry = 'Insurance' AND version_label = '1.0'
              AND source_model_id = (SELECT id FROM core.models WHERE name = 'ArchiMate 4')
              AND parent_model_id IS NULL
              FROM core.models WHERE id = v_ins), 'locked reference model created from the template';
    ASSERT (SELECT count(*) FROM core.entities WHERE model_id = v_ins) = 715, '715 entities';
    ASSERT (SELECT count(*) FROM core.relationships WHERE model_id = v_ins) = 248, '248 relationships';
    ASSERT (SELECT count(*) FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
             WHERE e.model_id = v_ins AND t.code = 'Capability') = 556, '556 capabilities';
    ASSERT (SELECT count(*) FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
             WHERE e.model_id = v_ins AND t.code = 'Capability' AND e.parent_entity_id IS NULL) = 12,
        'twelve level 1 capabilities, the rest have a parent';
    ASSERT NOT EXISTS (SELECT 1 FROM core.entities WHERE model_id = v_ins
                        AND (name ILIKE '%meridian%' OR description ILIKE '%meridian%')), 'made generic';
END $$;

-- the lock: every route of change is refused, the superuser included
SELECT pg_temp.expect_error($q$
    UPDATE core.entities SET name = 'Changed' WHERE model_id = (SELECT id FROM core.models WHERE name = 'Insurance reference model')
$q$, 'is locked');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.entities (model_id, entity_type_id, name)
    SELECT model_id, id, 'New' FROM core.entity_types
     WHERE code = 'Capability' AND model_id = (SELECT id FROM core.models WHERE name = 'Insurance reference model')
$q$, 'is locked');
SELECT pg_temp.expect_error($q$
    DELETE FROM core.relationships WHERE model_id = (SELECT id FROM core.models WHERE name = 'Insurance reference model')
$q$, 'is locked');
SELECT pg_temp.expect_error($q$
    UPDATE core.attribute_types SET name = 'Changed' WHERE model_id = (SELECT id FROM core.models WHERE name = 'Insurance reference model')
$q$, 'is locked');
SELECT pg_temp.expect_error($q$
    UPDATE core.models SET is_locked = false WHERE name = 'Insurance reference model'
$q$, 'is locked');
SELECT pg_temp.expect_error($q$
    DELETE FROM core.models WHERE name = 'ArchiMate 4'
$q$, 'is locked');
SELECT pg_temp.expect_error($q$ TRUNCATE core.entities CASCADE $q$, 'TRUNCATE');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.models (name, kind_code, is_locked) VALUES ('Fake reference', 'reference', true)
$q$, 'starts unlocked');   -- from 0.4.0 (D118); before: "Only the product installer"
SELECT pg_temp.expect_error($q$
    UPDATE core.models SET is_locked = true WHERE name = 'Sample insurance model'
$q$, 'go into the library');   -- from 0.4.0 (D118); before: "Only the product installer"
-- SET ROLE does not get round it: the check is on the session's login
SET LOCAL ROLE eax_migrator;
SELECT pg_temp.expect_error($q$
    UPDATE core.entities SET name = 'Changed' WHERE model_id = (SELECT id FROM core.models WHERE name = 'Insurance reference model')
$q$, 'is locked');
RESET ROLE;

-- an unlocked model can still be changed, and its properties set
DO $$
BEGIN
    UPDATE core.models SET owner = 'EA team', lifecycle = 'archived' WHERE name = 'Sample insurance model';
    ASSERT (SELECT lifecycle FROM core.models WHERE name = 'Sample insurance model') = 'archived', 'properties';
    UPDATE core.entities SET description = description || ' (checked)'
     WHERE model_id = (SELECT id FROM core.models WHERE name = 'Sample insurance model');
END $$;
SELECT pg_temp.expect_error($q$ UPDATE core.models SET lifecycle = 'gone' WHERE name = 'Sample insurance model' $q$, 'lifecycle');

SELECT 'phase 2 checks passed' AS result;
ROLLBACK;
