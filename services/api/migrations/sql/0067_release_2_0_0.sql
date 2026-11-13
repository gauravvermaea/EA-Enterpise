-- =====================================================================================
-- 0067_release_2_0_0: version 2.0.0, Release 2 (owner, 13 Nov 2026: "ready for release 2"; 21:02: "call it release2",
--   Release 1 being 1.0.0). Records the version only, so the API (version.toml 2.0.0) and the database agree; removes
--   the 1.1.0 row an installation may have from 0066 as first written. Rows only (D248).
-- =====================================================================================

DELETE FROM core.schema_versions WHERE version = '1.1.0';

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('2.0.0', '0067_release_2_0_0', 'Release 2')
ON CONFLICT (version) DO NOTHING;
