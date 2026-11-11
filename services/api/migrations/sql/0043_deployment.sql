-- =====================================================================================
-- 0043_deployment: version 0.19.0, the last set (D421): deployment kinds and eax deploy (phase 36, D498, D500 to D506)
--   Nothing in the database changes for deployment: eax deploy, the installer, the key vault and moving an
--   installation live in eaxcli; directory groups map to roles through the existing core.role_mappings rows, under
--   the key "group:<name>" (D503). It records the version and keeps the history of deployment targets:
--   * core.deployments: every deployment started from System admin > Deploy (D555 to D557), a plan or a real one:
--     the target (its address), the kind, the version given, who, when, how it ended, the address found. Copied from
--     the operations helper's run folders (work/deploys) by the API; secrets are never here. Rows only (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.19.0', '0043_deployment', 'The last set (D421): deployment kinds, eax deploy and its installer, directory groups mapped to roles, passwords from a key vault, moving an installation')
ON CONFLICT (version) DO NOTHING;   -- several 0.19.0 migrations (the last set): the first one writes the version

CREATE TABLE core.deployments (
    run_id       text PRIMARY KEY,                       -- the helper's run folder, e.g. 20261110T221500Z-1a2b3c
    target       text NOT NULL,                          -- the address people open, or user@address, or kind:name
    kind         text NOT NULL CHECK (kind IN ('server', 'aws', 'azure', 'digitalocean')),
    plan         boolean NOT NULL DEFAULT false,         -- a plan: nothing was run
    version      text NOT NULL DEFAULT '',               -- the release given to the target (a tag or branch)
    status       text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'failed', 'done', 'planned', 'quit', 'back')),
    started_by   text NOT NULL DEFAULT '',
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    address      text NOT NULL DEFAULT '',               -- the public address found (a cloud machine's IP)
    failed_step  text NOT NULL DEFAULT '',
    kept_credentials boolean NOT NULL DEFAULT false,     -- the person asked to keep them (kept by the helper, never here)
    recorded_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX deployments_target ON core.deployments (target, started_at DESC);
