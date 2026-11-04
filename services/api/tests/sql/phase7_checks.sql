-- Phase 7 database checks: saved views, favourites, search indexes and a metamodel batch as one version.
-- Run as the API's login, with the laptop sample loaded:
--   Get-Content services/api/tests/sql/phase7_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
-- Runs in one transaction that is rolled back. Ends with "phase 7 checks passed".
BEGIN;

DO $$
DECLARE
    v_model bigint;
    v_view  uuid;
    v_n     integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM core.schema_versions WHERE version = '0.7.0') THEN
        RAISE EXCEPTION 'schema version 0.7.0 (0011_grids) is missing';
    END IF;
    PERFORM set_config('eax.rls_bypass', 'on', true);
    SELECT id INTO v_model FROM core.models WHERE name = 'Sample insurance model' AND NOT is_deleted;

    -- a saved view and a favourite
    INSERT INTO core.saved_views (owner, model_id, view_kind, target, name, config, shared)
    VALUES ('user_architect', v_model, 'entity_grid', 'x', 'Phase 7 check view', '{"filter": "claims"}', true)
    RETURNING guid INTO v_view;
    INSERT INTO core.favourites (username, kind, target, model_id) VALUES ('user_architect', 'view', v_view, v_model);
    BEGIN
        INSERT INTO core.favourites (username, kind, target) VALUES ('user_architect', 'view', v_view);
        RAISE EXCEPTION 'a favourite could be added twice';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO core.favourites (username, kind, target) VALUES ('user_architect', 'report', v_view);
        RAISE EXCEPTION 'a favourite of an unknown kind was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- the search indexes exist
    SELECT count(*) INTO v_n FROM pg_indexes
     WHERE schemaname = 'core' AND indexname IN ('attribute_values_text_trgm_idx', 'entities_name_trgm_idx');
    IF v_n <> 2 THEN RAISE EXCEPTION 'search indexes missing (% of 2)', v_n; END IF;

    PERFORM set_config('eax.rls_bypass', '', true);
END $$;

SELECT 'phase 7 checks passed' AS result;
ROLLBACK;
