-- =====================================================================================
-- 0045_tests_scaling: version 0.19.0, the self-test (phase 36.1, D367, D522 to D525, D529) and scaling out (36.3)
--   * a self-test run: a smoke test (a few minutes) or detailed tests (API, browser, database, security), started from
--     System admin > Self-test or `eax test` (at once: never scheduled) or in CI. It runs on the live installation but
--     only in its own fixtures: every model, project, service account and credential it makes is named
--     self_test_<guid>_<n> (svc-self-test-<guid>-<role> for accounts) and listed in core.test_fixtures, so runs never
--     clash and their fixtures can be found and purged later, by hand (Self-test > Test fixtures)
--   * a test result: one check with its outcome, details and time; for a failure what was asked and what came back
--     (API), a screenshot and a video (browser), and the browser it ran in when watched in the admin's own browser
-- Scaling out (36.3) keeps its settings in the config file and its decisions in work/logs/scaling.jsonl: no table.
-- Rows only (D248): the runner and eax/testing decide everything.
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.19.0', '0045_tests_scaling', 'The last set: the self-test (36.1) and scaling out (36.3)')
ON CONFLICT (version) DO NOTHING;   -- several 0.19.0 migrations: the first one writes the version

CREATE TABLE core.test_runs (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_guid     uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- its fixtures are named self_test_<first 12 of it>_<n>
    started_by   text NOT NULL,
    trigger      text NOT NULL CHECK (trigger IN ('web', 'eax', 'ci', 'sample')),
    level        text NOT NULL DEFAULT 'smoke' CHECK (level IN ('smoke', 'detailed')),
    suites       text[] NOT NULL CHECK (suites <@ ARRAY['api', 'ui', 'db', 'security']::text[] AND cardinality(suites) > 0),
    role         text NOT NULL DEFAULT '' CHECK (role = '' OR role ~ '^[a-z-]+$'),        -- one role only; '' every role
    area         text NOT NULL DEFAULT '' CHECK (area = '' OR area ~ '^[a-z_]+$'),        -- one API area only; '' every area
    watch        boolean NOT NULL DEFAULT false,                 -- the browser journeys run in the admin's own browser
    browser      jsonb NOT NULL DEFAULT '{}',                    -- watch: {ticket, tokens, journeys, done}; emptied at the end
    state        text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'running', 'passed', 'failed', 'error', 'stopped')),
    step         text NOT NULL DEFAULT '',                       -- what it is doing now
    stop_asked   text NOT NULL DEFAULT '',                       -- who asked to stop it
    folder       text NOT NULL DEFAULT '' CHECK (folder ~ '^[A-Za-z0-9._-]{0,80}$'),   -- work/tests/<folder>: log, videos, report
    version      text NOT NULL DEFAULT '',
    passed       integer NOT NULL DEFAULT 0,
    failed       integer NOT NULL DEFAULT 0,
    skipped      integer NOT NULL DEFAULT 0,
    message      text NOT NULL DEFAULT '',
    purged_at    timestamptz,                                    -- its fixtures were removed (the report stays)
    purged_by    text,
    queued_at    timestamptz NOT NULL DEFAULT now(),
    started_at   timestamptz,
    finished_at  timestamptz
);
CREATE INDEX test_runs_recent_idx ON core.test_runs (queued_at DESC);

CREATE TABLE core.test_results (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id       bigint NOT NULL REFERENCES core.test_runs (id) ON DELETE CASCADE,
    suite        text NOT NULL CHECK (suite IN ('smoke', 'api', 'ui', 'db', 'security')),
    name         text NOT NULL CHECK (length(name) <= 400),
    outcome      text NOT NULL CHECK (outcome IN ('passed', 'failed', 'skipped', 'warning')),
    detail       text NOT NULL DEFAULT '' CHECK (length(detail) <= 20000),
    duration_ms  integer NOT NULL DEFAULT 0,
    screenshot   bytea,                                          -- a failed browser journey: what the page looked like
    video        text NOT NULL DEFAULT '',                       -- its video's file name in work/tests/<folder>
    browser      text NOT NULL DEFAULT '' CHECK (length(browser) <= 200),    -- watched in a browser: which and its version
    request      text NOT NULL DEFAULT '' CHECK (length(request) <= 4000),   -- a failed API check: what was asked
    response     text NOT NULL DEFAULT '' CHECK (length(response) <= 8000),  -- and what came back
    recorded_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX test_results_run_idx ON core.test_results (run_id, suite, outcome);

-- every fixture a run made; purged only by hand, and only what is listed here (D529)
CREATE TABLE core.test_fixtures (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id       bigint NOT NULL REFERENCES core.test_runs (id) ON DELETE RESTRICT,
    kind         text NOT NULL CHECK (kind IN ('model', 'project', 'service_account', 'credential')),
    ident        text NOT NULL,                                  -- a model's or project's guid, an account's name, a credential's guid
    name         text NOT NULL CHECK (name ~ '^(self_test_|svc-self-test-)'),
    created_at   timestamptz NOT NULL DEFAULT now(),
    purged_at    timestamptz,
    purged_by    text,
    UNIQUE (kind, ident)
);
CREATE INDEX test_fixtures_run_idx ON core.test_fixtures (run_id) WHERE purged_at IS NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.test_runs, core.test_results, core.test_fixtures TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
END;
$$;
