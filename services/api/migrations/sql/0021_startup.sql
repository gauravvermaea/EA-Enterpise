-- =====================================================================================
-- 0021_startup: build phase 12.1 (version 0.13.1), start-up in two tiers (D255)
--   * the core (database, sign-in, the API, the screens) starts first; everything else starts after it, in the
--     background: reports, documents, draw.io, backups, the operations helper, the laptop sample data and the first
--     data quality measurement
--   * what runs in the background after the API has started (eax/seed/later.py) writes how far it has got here, so
--     everyone sees it (red, amber, green with down, starting, up); no logic in the database (D248), just the rows
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.13.1', '0021_startup', 'Phase 12.1: start-up in two tiers, the start-up status, open diagrams in draw.io');

CREATE TABLE core.startup_parts (
    part        text PRIMARY KEY,                -- later: the sample data and start-up tasks after the API started
    name        text NOT NULL,
    state       text NOT NULL DEFAULT 'waiting' CHECK (state IN ('waiting', 'starting', 'up', 'down', 'skipped')),
    done        integer NOT NULL DEFAULT 0,
    total       integer NOT NULL DEFAULT 0,
    detail      text NOT NULL DEFAULT '',
    started_at  timestamptz,
    finished_at timestamptz,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.startup_parts IS 'How far the work started after the API is (sample data, demo estate, first quality measurement), D255';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.startup_parts TO eax_migrator;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.startup_parts TO eax_app;
    END IF;
END;
$$;
