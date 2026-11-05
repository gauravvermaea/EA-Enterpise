-- Phase 10 database checks: the administration console's settings (D183).
-- Run as the API's login:
--   Get-Content services/api/tests/sql/phase10_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
-- Runs in one transaction that is rolled back. Ends with "phase 10 checks passed".
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM core.schema_versions WHERE version = '0.10.0') THEN
        RAISE EXCEPTION 'schema version 0.10.0 (0016_settings) is missing';
    END IF;
    ASSERT (SELECT count(*) FROM core.settings) >= 13, 'the default settings';
    ASSERT (SELECT value #>> '{}' FROM core.settings WHERE key = 'time_zone') IS NOT NULL, 'a time zone';
    ASSERT has_table_privilege('eax_report', 'core.settings', 'SELECT'), 'reports read the formats';

    -- a change is kept in the history (and so reaches the change log)
    PERFORM set_config('eax.actor', 'check_user', true);
    UPDATE core.settings SET value = '"ZAR"', row_version = row_version + 1 WHERE key = 'base_currency';
    ASSERT EXISTS (SELECT 1 FROM history.row_versions WHERE table_name = 'settings' AND changed_by = 'check_user'), 'history';
    BEGIN
        INSERT INTO core.settings (key, value, name) VALUES ('Bad Key', '1', 'x');
        RAISE EXCEPTION 'a bad key was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- the gap report views read through definer functions (the report login has no access to core)
    ASSERT has_function_privilege('eax_report', 'rpt.f_gap_items()', 'EXECUTE'), 'gap items for reports';
END $$;

SELECT 'phase 10 checks passed' AS result;
ROLLBACK;
