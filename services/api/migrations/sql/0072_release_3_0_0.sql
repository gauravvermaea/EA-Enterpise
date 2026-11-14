-- =====================================================================================
-- 0072_release_3_0_0: version 3.0.0, Release 3 (owner, 14 Nov 2026, 09:55: "Lets close R3"; 09:56: "give me commands
--   in the meantime to publish R3"). Records the version only, so the API (version.toml 3.0.0) and the database agree
--   (the bug R4.18: the Release 3 self-test still showed 2.0.0). Rows only (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('3.0.0', '0072_release_3_0_0', 'Release 3')
ON CONFLICT (version) DO NOTHING;
