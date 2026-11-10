-- =====================================================================================
-- 0044_updates: version 0.19.0, updating to a new release (phase 36, D417, D510 to D516)
--   * core.update_history: every update and rollback of this installation, copied from the host's own record
--     (work/updates/history.json, kept by the updater) by the API, so it survives a lost work folder and the
--     reports can read it: from, to, the channel, who, when, the backup taken, the steps, the result. The host's record
--     comes first: the updater writes it even while the API and the database are down.
--   * notified: the administrators were told (a failed update, a finished one), once.
-- Rows only: which versions are offered, forward only, one release at a time, retry and roll back are in
-- eaxcli/releases.py, eaxcli/updater.py and services/ops/updates.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.19.0', '0044_updates', 'The last set: updating to a new release from git (D417), releases (8.5)')
ON CONFLICT (version) DO NOTHING;   -- several 0.19.0 migrations (the last set): the first one writes the version

CREATE TABLE IF NOT EXISTS core.update_history (
    id              text PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9._-]{1,60}$'),
    kind            text NOT NULL DEFAULT 'update' CHECK (kind IN ('update', 'rollback')),
    status          text NOT NULL CHECK (status IN ('running', 'failed', 'ok', 'rolling-back', 'rolled-back',
                                                     'not-started', 'scheduled', 'cancelled')),
    channel         text NOT NULL DEFAULT 'prod' CHECK (channel IN ('prod', 'rc', 'latest')),
    from_version    text NOT NULL DEFAULT '',
    from_commit     text NOT NULL DEFAULT '',
    to_version      text NOT NULL DEFAULT '',
    failed_version  text NOT NULL DEFAULT '',
    by_user         text NOT NULL DEFAULT '',
    started_at      timestamptz,
    finished_at     timestamptz,
    backup          text NOT NULL DEFAULT '',
    error           text NOT NULL DEFAULT '' CHECK (length(error) <= 4000),
    notes           text NOT NULL DEFAULT '' CHECK (length(notes) <= 20000),
    steps           jsonb NOT NULL DEFAULT '[]'::jsonb,
    sample          boolean NOT NULL DEFAULT false,        -- laptop sample rows (AGENTS.md)
    notified        text NOT NULL DEFAULT '',              -- the status the administrators were last told about
    recorded_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS update_history_started_idx ON core.update_history (started_at DESC NULLS LAST);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.update_history TO eax_app;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.update_history TO eax_migrator;
    END IF;
END;
$$;
