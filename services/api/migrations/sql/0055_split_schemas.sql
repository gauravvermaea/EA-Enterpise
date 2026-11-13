-- =====================================================================================
-- 0055_split_schemas: each part that can move lives in a schema of its own (D630; owner, 13 Nov 2026, 08:43 and 08:45:
--   "it can be in a seperate schema on same DB Server and database ... Ensure changes are different schemas with
--   different connection strings. This way when we want to scale out all we change is the location"; "ensure this DB
--   move is only limited to schemas no new DB server or DB is created").
--   tests (R2.28), operations (R2.27), archive (R2.41), personal (R2.53) and library_models (R2.42) are schemas in this
--   database. Each is reached by its own connection string (eax/databases.py); empty = this database. The tables move
--   with their rows, indexes, constraints, sequences and grants. No database is created. No version change.
-- =====================================================================================

CREATE SCHEMA IF NOT EXISTS tests;
CREATE SCHEMA IF NOT EXISTS operations;
CREATE SCHEMA IF NOT EXISTS archive;
CREATE SCHEMA IF NOT EXISTS personal;
CREATE SCHEMA IF NOT EXISTS library_models;

ALTER TABLE IF EXISTS core.test_runs        SET SCHEMA tests;
ALTER TABLE IF EXISTS core.test_results     SET SCHEMA tests;
ALTER TABLE IF EXISTS core.test_fixtures    SET SCHEMA tests;
ALTER TABLE IF EXISTS core.backup_schedules SET SCHEMA operations;
ALTER TABLE IF EXISTS core.deployments      SET SCHEMA operations;
ALTER TABLE IF EXISTS core.update_history   SET SCHEMA operations;
ALTER TABLE IF EXISTS core.heartbeat_logs   SET SCHEMA operations;
ALTER TABLE IF EXISTS core.startup_parts    SET SCHEMA operations;
ALTER TABLE IF EXISTS core.archive_store    SET SCHEMA archive;

COMMENT ON SCHEMA tests          IS 'D630: the self-test''s runs, results and fixtures (R2.28); EAX_TESTS_DB_URL';
COMMENT ON SCHEMA operations     IS 'D630: backups, deployments, updates, health, start-up (R2.27); EAX_OPERATIONS_DB_URL';
COMMENT ON SCHEMA archive        IS 'D630: archived and deleted models and projects (R2.41); EAX_ARCHIVE_DB_URL';
COMMENT ON SCHEMA personal       IS 'D630: each person''s notifications, requests, favourites, views, skills, settings (R2.53); EAX_PERSONAL_DB_URL';
COMMENT ON SCHEMA library_models IS 'D630: the read-only shared models (R2.42); EAX_LIBRARY_MODELS_DB_URL';

DO $$
DECLARE s text;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        FOREACH s IN ARRAY ARRAY['tests', 'operations', 'archive', 'personal', 'library_models'] LOOP
            EXECUTE format('GRANT USAGE ON SCHEMA %I TO eax_migrator', s);
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO eax_migrator', s);
            EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO eax_migrator', s);
        END LOOP;
    END IF;
END;
$$;
