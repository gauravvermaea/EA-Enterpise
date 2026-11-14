-- =====================================================================================
-- 0068_selftest_restore_suite: the self-test's sixth suite, restore (R3.8; owner, 13 Nov 2026: "test backup and
-- restore properly and completely in an automated manner from command line")
--   A run's suites and a result's suite may now be 'restore' too. Constraints only; no version change; no logic (D248).
-- =====================================================================================

ALTER TABLE IF EXISTS tests.test_runs DROP CONSTRAINT IF EXISTS test_runs_suites_check;
ALTER TABLE IF EXISTS tests.test_runs ADD CONSTRAINT test_runs_suites_check
    CHECK (suites <@ ARRAY['api', 'ui', 'db', 'security', 'backup', 'restore']::text[] AND cardinality(suites) > 0);

ALTER TABLE IF EXISTS tests.test_results DROP CONSTRAINT IF EXISTS test_results_suite_check;
ALTER TABLE IF EXISTS tests.test_results ADD CONSTRAINT test_results_suite_check
    CHECK (suite IN ('smoke', 'api', 'ui', 'db', 'security', 'backup', 'restore'));
