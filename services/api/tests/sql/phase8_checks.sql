-- Phase 8 database checks: commits of content, the Committer and History Viewer roles, draft rejection, merges (D165).
-- Run as the API's login, with the laptop sample loaded (the demo estate Protea Insurance):
--   Get-Content services/api/tests/sql/phase8_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
-- Runs in one transaction that is rolled back. Ends with "phase 8 checks passed".
BEGIN;

DO $$
DECLARE
    v_model bigint;
    v_set   bigint;
    v_ok    boolean;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM core.schema_versions WHERE version = '0.8.3') THEN
        RAISE EXCEPTION 'schema version 0.8.3 (0013_commits) is missing';
    END IF;

    -- six model roles, in order (D165, D151)
    ASSERT (SELECT array_agg(code ORDER BY sort_order) FROM core.app_roles WHERE scope = 'model')
         = ARRAY['model-admin', 'model-sub-admin', 'committer', 'architect', 'history-viewer', 'report-viewer'],
           'model roles: Model Admin, Model Sub Admin, Committer, Architect, History Viewer, Report Viewer';

    -- the tables of phase 8
    ASSERT to_regclass('core.change_sets') IS NOT NULL AND to_regclass('core.pending_changes') IS NOT NULL
       AND to_regclass('core.commits') IS NOT NULL AND to_regclass('core.commit_items') IS NOT NULL
       AND to_regclass('core.merge_sessions') IS NOT NULL, 'change sets, pending changes, commits, commit items, merge sessions';

    -- uncommitted changes never reach the report login (only committed content is reported, D165)
    ASSERT NOT has_table_privilege('eax_report', 'core.pending_changes', 'SELECT'), 'reports cannot read uncommitted changes';
    ASSERT NOT has_table_privilege('eax_report', 'core.change_sets', 'SELECT'), 'reports cannot read change sets';

    -- a Committer may change content (the database checks the person who writes, also when committing)
    PERFORM set_config('eax.rls_bypass', 'on', true);
    SELECT id INTO v_model FROM core.models WHERE name = 'Protea Insurance (demo estate)';
    PERFORM set_config('eax.rls_bypass', '', true);
    ASSERT v_model IS NOT NULL, 'the demo estate is loaded';
    PERFORM set_config('eax.actor', 'user_committer', true);
    PERFORM set_config('eax.user_roles', 'user', true);
    ASSERT core.why_not(v_model, 'content') IS NULL, 'a Committer changes content';
    ASSERT core.why_not(v_model, 'metamodel') IS NOT NULL, 'a Committer does not change the metamodel';
    PERFORM set_config('eax.actor', 'user_report_viewer', true);
    ASSERT core.why_not(v_model, 'content') IS NOT NULL, 'a Report Viewer does not change content';

    -- one open change set per person and model
    PERFORM set_config('eax.actor', '', true);
    PERFORM set_config('eax.user_roles', '', true);
    INSERT INTO core.change_sets (model_id, author) VALUES (v_model, 'check_person') RETURNING id INTO v_set;
    BEGIN
        INSERT INTO core.change_sets (model_id, author) VALUES (v_model, 'check_person');
        RAISE EXCEPTION 'two open change sets for one person';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    -- only known changes and states
    BEGIN
        INSERT INTO core.pending_changes (model_id, change_set_id, author, op, args) VALUES (v_model, v_set, 'check_person', 'metamodel.drop', '{}');
        RAISE EXCEPTION 'an unknown change was kept';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    INSERT INTO core.pending_changes (model_id, change_set_id, author, op, args, label)
    VALUES (v_model, v_set, 'check_person', 'entity.update', '{"entity": "x", "data": {}}', 'check');
    BEGIN
        UPDATE core.pending_changes SET status = 'lost' WHERE change_set_id = v_set;
        RAISE EXCEPTION 'an unknown status was kept';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- commit numbers are per model
    INSERT INTO core.commits (model_id, number, committed_by, authors) VALUES (v_model, 100001, 'check_person', ARRAY['check_person']);
    BEGIN
        INSERT INTO core.commits (model_id, number, committed_by, authors) VALUES (v_model, 100001, 'check_person', ARRAY['check_person']);
        RAISE EXCEPTION 'two commits with one number';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    -- a draft model can be rejected and opened again (D165)
    SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'models_approval_state_check'
                    AND pg_get_constraintdef(oid) LIKE '%rejected%') INTO v_ok;
    ASSERT v_ok, 'approval state rejected';
    SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'core.model_publish_events'::regclass AND contype = 'c'
                    AND pg_get_constraintdef(oid) LIKE '%reopened%') INTO v_ok;
    ASSERT v_ok, 'publish events rejected and reopened';
END $$;

SELECT 'phase 8 checks passed' AS result;
ROLLBACK;
