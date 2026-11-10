-- =====================================================================================
-- 0043_deployment: version 0.19.0, the last set (D421): deployment kinds and eax deploy (phase 36, D498, D500 to D506)
--   Nothing in the database changes for deployment: eax deploy, the installer, the key vault and moving an
--   installation live in eaxcli; directory groups map to roles through the existing core.role_mappings rows, under
--   the key "group:<name>" (D503). This migration only records the version.
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.19.0', '0043_deployment', 'The last set (D421): deployment kinds, eax deploy and its installer, directory groups mapped to roles, passwords from a key vault, moving an installation')
ON CONFLICT (version) DO NOTHING;   -- several 0.19.0 migrations (the last set): the first one writes the version
