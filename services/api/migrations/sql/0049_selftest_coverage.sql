-- =====================================================================================
-- 0049_selftest_coverage: version 0.19.0, the self-test covers the app (D575 to D578)
--   A run may ask for one or more browser journeys only (by part of their names) or only the page sweep (every page,
--   group, tab and sub-tab opened and checked); both are kept with the run so the report and the History say what ran,
--   and the command it equals.
-- Rows only (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.19.0', '0049_selftest_coverage', 'The self-test covers every page and real journeys')
ON CONFLICT (version) DO NOTHING;

ALTER TABLE core.test_runs
    ADD COLUMN IF NOT EXISTS journeys   text[]  NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS pages_only boolean NOT NULL DEFAULT false;
