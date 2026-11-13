-- Phase 8.4 checks (as the API's login): the version, and model tags of kind 'backup' (D216).
\set ON_ERROR_STOP on
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM core.schema_versions WHERE version = '0.12.0' AND migration = '0019_backups') THEN
        RAISE EXCEPTION 'version 0.12.0 not recorded';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'core.model_tags'::regclass
                    AND pg_get_constraintdef(oid) LIKE '%backup%') THEN
        RAISE EXCEPTION 'model_tags kind backup missing';
    END IF;
    RAISE NOTICE 'phase 8.4 checks passed';
END $$;
DO $$
BEGIN
    IF (SELECT count(*) FROM operations.backup_schedules) <> 2 THEN
        RAISE EXCEPTION 'backup schedules missing';
    END IF;
    IF NOT (SELECT enabled AND cron = '0 1 * * *' AND keep = 7 FROM operations.backup_schedules WHERE kind = 'infrastructure') THEN
        RAISE EXCEPTION 'nightly infrastructure schedule not set up';
    END IF;
    BEGIN
        UPDATE operations.backup_schedules SET keep = 0 WHERE kind = 'application';
        RAISE EXCEPTION 'keep 0 accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        UPDATE operations.backup_schedules SET cron = 'every night' WHERE kind = 'application';
        RAISE EXCEPTION 'a bad schedule accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    RAISE NOTICE 'phase 8.4 schedule checks passed';
END $$;
