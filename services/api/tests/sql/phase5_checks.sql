-- Phase 5 database checks: report views, typed views kept in step with the metamodel (D139), the
-- standard reports (D140) and model access for reports (D138).
-- Run as the API's login (it owns the tables), with the laptop sample loaded:
--   Get-Content services/api/tests/sql/phase5_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
-- Runs in one transaction that is rolled back. Ends with "phase 5 checks passed".
BEGIN;

DO $$
DECLARE
    v_n bigint;
    v_view text;
    v_model bigint;
    v_type bigint;
BEGIN
    -- every report view the dashboards read exists and answers
    FOREACH v_view IN ARRAY ARRAY['models', 'entities', 'entity_values', 'relationships', 'changes', 'model_access',
        'catalogue', 'entity_pairs', 'std_roles', 'entity_std', 'sr01_application_inventory', 'sr02_capability_catalogue',
        'sr03_technology_inventory', 'sr04_data_catalogue', 'sr05_process_catalogue', 'sr06_interfaces', 'sr07_actors',
        'sr08_motivation', 'sr_matrix', 'mo_type_counts', 'mo_recent_changes', 'mo_pick_list_counts'] LOOP
        IF to_regclass('rpt.' || v_view) IS NULL THEN
            RAISE EXCEPTION 'report view rpt.% is missing', v_view;
        END IF;
        EXECUTE format('SELECT count(*) FROM (SELECT * FROM rpt.%I LIMIT 1) q', v_view) INTO v_n;
    END LOOP;

    -- the report login reads the views and nothing else
    IF NOT has_table_privilege('eax_report', 'rpt.sr01_application_inventory', 'SELECT') THEN
        RAISE EXCEPTION 'eax_report cannot read rpt.sr01_application_inventory';
    END IF;
    IF has_table_privilege('eax_report', 'core.entities', 'SELECT') THEN
        RAISE EXCEPTION 'eax_report must not read core.entities directly';
    END IF;
    IF has_table_privilege('eax_report', 'core.known_users', 'SELECT') THEN
        RAISE EXCEPTION 'eax_report must not read core.known_users';
    END IF;

    -- content is there: the views see every model, whoever runs them
    SELECT count(*) INTO v_n FROM rpt.models;
    IF v_n < 3 THEN RAISE EXCEPTION 'rpt.models shows % models, expected the built-in ones', v_n; END IF;
    SELECT count(*) INTO v_n FROM rpt.sr02_capability_catalogue;
    IF v_n = 0 THEN RAISE EXCEPTION 'SR-02 capability catalogue is empty'; END IF;
    SELECT count(*) INTO v_n FROM rpt.sr_matrix WHERE a_role = 'capability' AND b_role = 'value_stream';
    IF v_n = 0 THEN RAISE EXCEPTION 'the capability x value stream matrix is empty'; END IF;

    -- typed views: one per entity type in use, one column per attribute
    IF to_regclass('rpt.t_application_component') IS NULL THEN
        RAISE EXCEPTION 'typed view rpt.t_application_component is missing (run rpt.refresh_typed_views after the seed)';
    END IF;
    PERFORM rpt.refresh_typed_views();
    SELECT rpt.refresh_typed_views() INTO v_n;
    IF v_n <> 0 THEN RAISE EXCEPTION 'a second refresh changed % views; it should change none', v_n; END IF;

    -- a new entity type in a working model gets its view; retiring it removes the view
    SELECT id INTO v_model FROM core.models WHERE name = 'Karoo Re (independent)' AND NOT is_deleted;
    IF v_model IS NULL THEN RAISE EXCEPTION 'the laptop test model Karoo Re is missing (load the sample)'; END IF;
    PERFORM set_config('eax.rls_bypass', 'on', true);
    INSERT INTO core.entity_types (model_id, layer_id, code, name, table_name, id_prefix)
    SELECT v_model, layer_id, 'Phase5CheckType', 'Phase 5 check type', 'phase5_check_type', 'P5C'
      FROM core.entity_types WHERE model_id = v_model AND NOT is_deleted LIMIT 1
    RETURNING id INTO v_type;
    PERFORM rpt.refresh_typed_views();
    IF to_regclass('rpt.t_phase5_check_type') IS NULL THEN
        RAISE EXCEPTION 'a new entity type got no typed view';
    END IF;
    UPDATE core.entity_types SET is_deleted = true WHERE id = v_type;
    PERFORM rpt.refresh_typed_views();
    IF to_regclass('rpt.t_phase5_check_type') IS NOT NULL THEN
        RAISE EXCEPTION 'the typed view of a removed entity type is still there';
    END IF;
    PERFORM set_config('eax.rls_bypass', '', true);

    -- model access (D138): model roles, the models above them, the published library; Super Admins everything
    INSERT INTO core.known_users (username, roles) VALUES ('phase5_super', '{super-admin}'), ('phase5_viewer', '{user}')
        ON CONFLICT (username) DO UPDATE SET roles = EXCLUDED.roles;
    SELECT count(*) INTO v_n FROM rpt.models m
     WHERE m.model_id NOT IN (SELECT model_id FROM rpt.model_access WHERE username = 'phase5_super');
    IF v_n <> 0 THEN RAISE EXCEPTION 'a Super Admin misses % models in the reports', v_n; END IF;
    SELECT count(*) INTO v_n FROM rpt.model_access a JOIN core.models m ON m.id = a.model_id
     WHERE a.username = 'phase5_viewer' AND m.kind_code = 'project';
    IF v_n <> 0 THEN RAISE EXCEPTION 'someone with no model roles sees % working models in the reports', v_n; END IF;
    SELECT count(*) INTO v_n FROM rpt.model_access WHERE username = 'phase5_viewer';
    IF v_n = 0 THEN RAISE EXCEPTION 'the published library is missing from everyone''s reports'; END IF;
    IF EXISTS (SELECT 1 FROM core.model_users WHERE username = 'user_report_viewer') THEN
        SELECT count(*) INTO v_n FROM core.model_users u
         WHERE u.username = 'user_report_viewer'
           AND u.model_id NOT IN (SELECT model_id FROM rpt.model_access WHERE username = 'user_report_viewer');
        IF v_n <> 0 THEN RAISE EXCEPTION 'the Report Viewer misses % of their models in the reports', v_n; END IF;
    END IF;
END $$;

SELECT 'phase 5 checks passed' AS result;
ROLLBACK;
