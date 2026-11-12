-- =====================================================================================
-- 0051_selftest_repeat: run the failed ones again (R2.36, D605; owner, 12 Nov 2026)
--   A run may repeat the checks that failed in an earlier run (repeat_of; with its warnings too: repeat_warnings).
--   The run keeps the ids of the fixtures it made (fixture_ids), so a page of its own model is matched to the same page
--   of the repeat's model. When every repeated check passes, the earlier run records the repeat (followed_up_by).
--   No version change. Rows only (D248).
-- =====================================================================================

ALTER TABLE core.test_runs
    ADD COLUMN IF NOT EXISTS repeat_of       bigint  REFERENCES core.test_runs (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS repeat_warnings boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS followed_up_by  bigint  REFERENCES core.test_runs (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS fixture_ids     jsonb   NOT NULL DEFAULT '{}'::jsonb;
