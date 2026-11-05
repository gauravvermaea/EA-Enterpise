-- Phase 8.3 database checks: model tags, comparison profiles, gap analyses and their report views (D172).
-- Run as the API's login, with the laptop sample loaded (the demo estate Protea Insurance):
--   Get-Content services/api/tests/sql/phase8_3_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
-- Runs in one transaction that is rolled back. Ends with "phase 8.3 checks passed".
BEGIN;

DO $$
DECLARE
    v_model bigint;
    v_tag   bigint;
    v_gap   bigint;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM core.schema_versions WHERE version = '0.8.4') THEN
        RAISE EXCEPTION 'schema version 0.8.4 (0014_tags) is missing';
    END IF;
    ASSERT to_regclass('core.model_tags') IS NOT NULL AND to_regclass('core.compare_profiles') IS NOT NULL
       AND to_regclass('core.gap_analyses') IS NOT NULL AND to_regclass('core.gap_items') IS NOT NULL
       AND to_regclass('core.gap_runs') IS NOT NULL, 'the phase 8.3 tables';
    ASSERT to_regclass('rpt.gap_analyses') IS NOT NULL AND to_regclass('rpt.gap_items') IS NOT NULL
       AND to_regclass('rpt.gap_matrix') IS NOT NULL, 'the gap report views';
    ASSERT has_table_privilege('eax_report', 'rpt.gap_items', 'SELECT'), 'reports read the gaps';
    ASSERT NOT has_table_privilege('eax_report', 'core.model_tags', 'SELECT'), 'reports do not read the snapshots';

    PERFORM set_config('eax.rls_bypass', 'on', true);
    SELECT id INTO v_model FROM core.models WHERE name = 'Protea Insurance (demo estate)';
    PERFORM set_config('eax.rls_bypass', '', true);
    ASSERT v_model IS NOT NULL, 'the demo estate is loaded';

    -- a restore is a commit of its own kind
    INSERT INTO core.commits (model_id, number, kind, committed_by, authors) VALUES (v_model, 900001, 'restore', 'check', ARRAY['check']);

    -- tags: one name per model; a locked tag is never changed or deleted
    INSERT INTO core.model_tags (model_id, name, spec, snapshot, created_by) VALUES (v_model, 'Check tag', '{}', '{}', 'check')
        RETURNING id INTO v_tag;
    BEGIN
        INSERT INTO core.model_tags (model_id, name, spec, snapshot, created_by) VALUES (v_model, 'check TAG', '{}', '{}', 'check');
        RAISE EXCEPTION 'two tags with one name';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    UPDATE core.model_tags SET is_locked = true WHERE id = v_tag;
    BEGIN
        UPDATE core.model_tags SET name = 'Changed' WHERE id = v_tag;
        RAISE EXCEPTION 'a locked tag was renamed';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        DELETE FROM core.model_tags WHERE id = v_tag;
        RAISE EXCEPTION 'a locked tag was deleted';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    UPDATE core.model_tags SET restored_at = now(), restored_by = 'check' WHERE id = v_tag;   -- restoring is recorded
    UPDATE core.model_tags SET is_locked = false WHERE id = v_tag;
    DELETE FROM core.model_tags WHERE id = v_tag;

    -- gap analyses: the gaps reach the report views (gone gaps do not)
    INSERT INTO core.gap_analyses (model_id, name, template, baseline, target, compared_by, created_by)
    VALUES (v_model, 'Check gaps', 'application', '{"label": "Baseline"}', '{"label": "Target"}', 'check', 'check') RETURNING id INTO v_gap;
    INSERT INTO core.gap_items (analysis_id, match_key, entity_type, name, status, resolution) VALUES
        (v_gap, 'a|', 'ApplicationComponent', 'Old system', 'eliminated', 'Retire'),
        (v_gap, '|b', 'ApplicationComponent', 'New system', 'new', ''),
        (v_gap, 'c|c', 'ApplicationComponent', 'Kept system', 'kept', ''),
        (v_gap, 'd|', 'ApplicationComponent', 'Gone', 'eliminated', '');
    UPDATE core.gap_items SET gone = true WHERE analysis_id = v_gap AND name = 'Gone';
    BEGIN
        INSERT INTO core.gap_items (analysis_id, match_key, entity_type, name, status) VALUES (v_gap, 'x', 'X', 'x', 'missing');
        RAISE EXCEPTION 'an unknown gap status';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    ASSERT (SELECT count(*) FROM rpt.gap_items WHERE gap_analysis = 'Check gaps') = 3, 'gone gaps are left out';
    ASSERT (SELECT undecided FROM rpt.gap_analyses WHERE gap_analysis = 'Check gaps') = 1, 'one gap without a resolution';
    -- each result of an analysis is a numbered run, one number once
    INSERT INTO core.gap_runs (analysis_id, number, compared_by, baseline, target) VALUES (v_gap, 1, 'check', '{}', '{}');
    BEGIN
        INSERT INTO core.gap_runs (analysis_id, number, compared_by, baseline, target) VALUES (v_gap, 1, 'check', '{}', '{}');
        RAISE EXCEPTION 'two runs with one number';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    ASSERT (SELECT togaf_cell FROM rpt.gap_matrix WHERE gap_analysis = 'Check gaps' AND status = 'eliminated')
         LIKE 'Eliminated%', 'TOGAF cell';
END $$;

SELECT 'phase 8.3 checks passed' AS result;
ROLLBACK;
