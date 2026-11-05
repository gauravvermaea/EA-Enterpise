-- Phase 10.1 (0.10.1): import and export sheets. Run as the API's login after a clean start.
DO $$
BEGIN
    ASSERT (SELECT version FROM core.schema_versions ORDER BY applied_at DESC, version DESC LIMIT 1) IS NOT NULL, 'schema versions';
    ASSERT EXISTS (SELECT 1 FROM core.schema_versions WHERE version = '0.10.1'), 'version 0.10.1 recorded';
    ASSERT to_regclass('core.loads') IS NOT NULL, 'loads';
    ASSERT to_regclass('core.column_mappings') IS NOT NULL, 'column mappings';
    ASSERT to_regclass('core.task_files') IS NOT NULL, 'task files';
    ASSERT (SELECT data_type FROM information_schema.columns WHERE table_schema = 'core' AND table_name = 'loads'
             AND column_name = 'change_ids') = 'ARRAY', 'a load keeps the changes it became';
    ASSERT (SELECT udt_name FROM information_schema.columns WHERE table_schema = 'core' AND table_name = 'loads'
             AND column_name = 'change_ids') = '_uuid', 'by their guid';
    RAISE NOTICE 'phase 10.1 checks passed';
END;
$$;
