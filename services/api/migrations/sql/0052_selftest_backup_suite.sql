-- =====================================================================================
-- 0052_selftest_backup_suite: the self-test's fifth suite, backup (R2.45, D608; owner, 12 Nov 2026: "do u test
-- application backup and infra backup in your testing? If not it should be")
--   A run's suites and a result's suite may now be 'backup' too. Constraints only; no version change; no logic (D248).
-- =====================================================================================

ALTER TABLE core.test_runs DROP CONSTRAINT IF EXISTS test_runs_suites_check;
ALTER TABLE core.test_runs ADD CONSTRAINT test_runs_suites_check
    CHECK (suites <@ ARRAY['api', 'ui', 'db', 'security', 'backup']::text[] AND cardinality(suites) > 0);

ALTER TABLE core.test_results DROP CONSTRAINT IF EXISTS test_results_suite_check;
ALTER TABLE core.test_results ADD CONSTRAINT test_results_suite_check
    CHECK (suite IN ('smoke', 'api', 'ui', 'db', 'security', 'backup'));
