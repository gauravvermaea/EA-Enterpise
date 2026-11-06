-- 0019_backups: build phase 8.4 (version 0.12.0), backups and restores (D216, D217, D222).
-- The backups themselves live in files (EAX_BACKUP_DIR: infrastructure/ and application/), never in the database, so a
-- database restore cannot lose the list of backups. When and how many: core.backup_schedules, one row per kind, changed
-- by IT and Super Admins on Administration > Backups (nothing about backups in the config file, D222). A model put back
-- from a model backup gets a tag of kind 'backup' (core.model_tags, 0014).

CREATE TABLE core.backup_schedules (
    kind        text PRIMARY KEY CHECK (kind IN ('infrastructure', 'application')),
    enabled     boolean NOT NULL DEFAULT true,
    cron        text NOT NULL CHECK (cron ~ '^\S+ \S+ \S+ \S+ \S+$'),   -- minute hour day month weekday, the installation's time zone
    tag         text NOT NULL DEFAULT 'scheduled' CHECK (btrim(tag) <> '' AND length(tag) <= 60),
    keep        integer NOT NULL DEFAULT 7 CHECK (keep BETWEEN 1 AND 365),
    warn_after_hours integer NOT NULL DEFAULT 36 CHECK (warn_after_hours BETWEEN 1 AND 8760),  -- health: the newest is too old
    last_run_at timestamptz,
    last_status text NOT NULL DEFAULT '',
    updated_by  text NOT NULL DEFAULT 'system',
    updated_at  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.backup_schedules IS 'When backups run and how many are kept, per kind (phase 8.4, D222); managed in the console';
INSERT INTO core.backup_schedules (kind, enabled, cron, tag, keep) VALUES
    ('infrastructure', true, '0 1 * * *', 'nightly', 7),
    ('application', true, '0 2 * * 0', 'weekly', 7);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        REVOKE ALL ON core.backup_schedules FROM eax_report;    -- operational: never in reports
    END IF;
END;
$$;

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.12.0', '0019_backups', 'Phase 8.4: infrastructure and application backups, model backups, restores');
