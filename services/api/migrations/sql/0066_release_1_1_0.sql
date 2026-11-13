-- =====================================================================================
-- 0066_release_1_1_0: version 1.1.0, Release 2 (owner, 13 Nov 2026: "ready for release 2")
--   Records the version only, so the API (version.toml 1.1.0) and the database agree. Rows only (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('1.1.0', '0066_release_1_1_0', 'Release 2')
ON CONFLICT (version) DO NOTHING;
