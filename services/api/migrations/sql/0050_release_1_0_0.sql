-- =====================================================================================
-- 0050_release_1_0_0: version 1.0.0, Release 1 (owner, 11 Nov 2026)
--   Release 1 is 0.19.0 with the last fixes; this records the version only, so the API (version.toml 1.0.0) and the
--   database agree. Rows only (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('1.0.0', '0050_release_1_0_0', 'Release 1')
ON CONFLICT (version) DO NOTHING;
