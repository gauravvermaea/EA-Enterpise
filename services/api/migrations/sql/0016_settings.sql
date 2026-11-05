-- =====================================================================================
-- 0016_settings: build phase 10 (version 0.10.0), the administration console's settings (D156, D182, D183)
--   * core.settings: the settings the running system reads, changed on screen by Super Admins and applied at once:
--     application settings (base currency and symbol, country, time zone, date and number formats, first day of the
--     week, the month the financial year starts) and runtime system settings (largest upload, how long change log
--     entries are kept, session time-outs). Start-up settings stay in the config file (shown in the console).
--   * every change is in the history (and so in the change log) like any other row
--   * core.tasks: long work run in the background (first: tagging a model), followed on screen until done (D192)
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.10.0', '0016_settings', 'Phase 10: application and runtime settings changed in the administration console');

CREATE TABLE core.settings (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    key         text NOT NULL UNIQUE CHECK (key ~ '^[a-z][a-z0-9_]*$'),
    value       jsonb NOT NULL,
    name        text NOT NULL,                 -- shown in the history and the change log
    modified_at timestamptz NOT NULL DEFAULT now(),
    modified_by text NOT NULL DEFAULT core.current_actor(),
    row_version integer NOT NULL DEFAULT 1
);
COMMENT ON TABLE core.settings IS 'Phase 10: settings the running system reads, changed by Super Admins in the administration console';
CREATE TRIGGER settings_history AFTER INSERT OR UPDATE OR DELETE ON core.settings FOR EACH ROW EXECUTE FUNCTION history.capture();

-- the defaults (D156): an installation changes them on screen
INSERT INTO core.settings (key, value, name) VALUES
    ('base_currency', '"USD"', 'Base currency'),
    ('currency_symbol', '"$"', 'Currency symbol'),
    ('country', '"South Africa"', 'Country or region'),
    ('time_zone', '"Africa/Johannesburg"', 'Time zone'),
    ('date_format', '"YYYY-MM-DD"', 'Date format'),
    ('decimal_separator', '"."', 'Decimal separator'),
    ('thousands_separator', '" "', 'Thousands separator'),
    ('first_day_of_week', '"Monday"', 'First day of the week'),
    ('financial_year_start', '3', 'Month the financial year starts'),
    ('upload_max_mb', '50', 'Largest upload (MB)'),
    ('change_log_keep_days', '730', 'Keep change log entries (days)'),
    ('session_idle_minutes', '60', 'Signed out after idle (minutes)'),
    ('session_max_hours', '10', 'Longest session (hours)'),
    ('log_level', '"INFO"', 'Log level');

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        GRANT SELECT ON core.settings TO eax_report;   -- reports follow the installation's formats (D182)
    END IF;
END;
$$;

-- long work in the background (D192): the screen that asked follows it until it is done and says so; also through the
-- API. The job runner (eax/jobs.py) does the work as the person who asked
CREATE TABLE core.tasks (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid          uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    kind          text NOT NULL,                         -- tag.create, ... (eax/tasks.py)
    model_id      bigint REFERENCES core.models (id) ON DELETE CASCADE,
    label         text NOT NULL,                         -- what it does, in words: "Tag Protea Insurance as Baseline 2026"
    params        jsonb NOT NULL DEFAULT '{}',
    status        text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    message       text NOT NULL DEFAULT '',              -- the outcome or the error, in words
    result        jsonb NOT NULL DEFAULT '{}',
    job_id        bigint,                                -- the job runner's job
    requested_by  text NOT NULL,
    requested_at  timestamptz NOT NULL DEFAULT now(),
    started_at    timestamptz,
    finished_at   timestamptz
);
CREATE INDEX tasks_by_idx ON core.tasks (requested_by, requested_at DESC);
COMMENT ON TABLE core.tasks IS 'Phase 10: long work done in the background and followed on screen until it is done (D192)';
