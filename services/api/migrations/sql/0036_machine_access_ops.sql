-- =====================================================================================
-- 0036_machine_access_ops: version 0.17.0, machine access (phase 25, D366, D378, D438 to D441) and operations insight and
-- housekeeping (phases 35 and 35.1, D371, D442 to D445)
--   * service accounts: a name other systems sign in as, with global roles given by a Super Admin or IT Admin; their
--     model roles are given like anyone's (core.model_users)
--   * machine credentials: a token, an API key or a client certificate, for a person or a service account, each with an
--     expiry, read or read-write per API area, optionally only some models or projects, revoke and last used. Secrets are
--     kept only as a SHA-256 hash; certificates by their SHA-256 fingerprint (self-signed ones trusted one by one)
--   * usage per day (who, which part, which model), retention rules, housekeeping runs and the archive
-- Rows only: the rules are in eax/machine_access.py and eax/operations.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.17.0', '0036_machine_access_ops', 'Batch 1 (D421): machine access; operations insight and housekeeping')
ON CONFLICT (version) DO NOTHING;   -- several 0.17.0 migrations (batch 1): the first one writes the version

-- ---------------------------------------------------------------- machine access (phase 25)
CREATE TABLE core.service_accounts (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    username     text NOT NULL UNIQUE CHECK (username = lower(username) AND username ~ '^svc-[a-z0-9][a-z0-9-]{1,40}$'),
    name         text NOT NULL CHECK (btrim(name) <> ''),
    description  text NOT NULL DEFAULT '',
    roles        text[] NOT NULL DEFAULT '{user}',      -- global roles (eax.permissions.GLOBAL_ROLES)
    created_by   text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    disabled_at  timestamptz,
    disabled_by  text
);
COMMENT ON TABLE core.service_accounts IS 'Phase 25 (D366): accounts other systems sign in as; made by Super Admins and IT Admins';

CREATE TABLE core.machine_credentials (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid             uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    owner            text NOT NULL CHECK (owner = lower(owner) AND owner <> ''),   -- a person or a service account (svc-...)
    kind             text NOT NULL CHECK (kind IN ('token', 'api_key', 'certificate')),
    name             text NOT NULL CHECK (btrim(name) <> ''),
    secret_prefix    text NOT NULL DEFAULT '',          -- the first characters, to recognise it (tokens and keys)
    secret_hash      text UNIQUE,                       -- SHA-256 of the secret; the secret itself is shown once
    cert_fingerprint text UNIQUE,                       -- SHA-256 of the certificate (DER), lower-case hex
    cert_subject     text NOT NULL DEFAULT '',
    cert_not_after   timestamptz,
    cert_pem         text NOT NULL DEFAULT '',
    scopes           jsonb NOT NULL DEFAULT '{}',       -- {area: "read" | "read-write"}; an area left out is refused
    model_guids      uuid[] NOT NULL DEFAULT '{}',      -- only these models (empty: every model the owner may use)
    project_guids    uuid[] NOT NULL DEFAULT '{}',      -- only these projects (empty: every project the owner may use)
    expires_at       timestamptz NOT NULL,
    created_by       text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    revoked_at       timestamptz,
    revoked_by       text,
    revoke_reason    text NOT NULL DEFAULT '',
    last_used_at     timestamptz,
    last_used_from   text NOT NULL DEFAULT '',
    last_used_path   text NOT NULL DEFAULT '',
    use_count        bigint NOT NULL DEFAULT 0,
    CHECK ((kind = 'certificate') = (cert_fingerprint IS NOT NULL)),
    CHECK ((kind <> 'certificate') = (secret_hash IS NOT NULL))
);
CREATE INDEX machine_credentials_owner_idx ON core.machine_credentials (owner, created_at DESC);
COMMENT ON TABLE core.machine_credentials IS 'Phase 25 (D366, D378): tokens, API keys and client certificates with their scopes';

-- ---------------------------------------------------------------- operations insight (phase 35)
CREATE TABLE core.usage_daily (
    day       date NOT NULL,
    username  text NOT NULL,
    area      text NOT NULL,             -- the API area (eax.machine_access.AREAS) or "screens"
    feature   text NOT NULL,             -- the part of it: /api/v1/<feature>/...
    model_guid text NOT NULL DEFAULT '', -- the model the call was about (its address); empty: none
    machine   boolean NOT NULL DEFAULT false,   -- made with a machine credential (phase 25)
    calls     integer NOT NULL DEFAULT 0,
    PRIMARY KEY (day, username, area, feature, model_guid, machine)
);
CREATE INDEX usage_daily_model_idx ON core.usage_daily (model_guid, day);
COMMENT ON TABLE core.usage_daily IS 'Phase 35 (D371): calls per day, person, part and model; counted by the API';

-- ---------------------------------------------------------------- housekeeping (phase 35.1)
CREATE TABLE core.retention_rules (
    code        text PRIMARY KEY,           -- eax.operations.RULES
    action      text NOT NULL CHECK (action IN ('keep', 'archive', 'delete')),
    after_days  integer NOT NULL CHECK (after_days BETWEEN 1 AND 36500),
    set_by      text NOT NULL DEFAULT 'installation',
    set_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.retention_rules IS 'Phase 35.1 (D371): what housekeeping keeps, archives or deletes, and after how long';

CREATE TABLE core.housekeeping_runs (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    dry_run      boolean NOT NULL,
    started_by   text NOT NULL,           -- a person, or "schedule"
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    rules        jsonb NOT NULL DEFAULT '{}',   -- the rules as they were
    results      jsonb NOT NULL DEFAULT '{}',   -- {rule: {found, archived, deleted, kept, note}}
    confirmed_at timestamptz,             -- a dry run confirmed: the scheduled runs may act
    confirmed_by text,
    status       text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'failed')),
    message      text NOT NULL DEFAULT ''
);
COMMENT ON TABLE core.housekeeping_runs IS 'Phase 35.1 (D371): each housekeeping run; the first is a dry run to confirm';

CREATE TABLE core.archived_items (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rule         text NOT NULL,           -- the retention rule that archived it
    source_table text NOT NULL,
    source_id    bigint NOT NULL,
    model_id     bigint,                  -- no reference: the model may go later
    summary      text NOT NULL DEFAULT '',
    data         jsonb NOT NULL,          -- the row as it was (files: without their content)
    content      bytea,                   -- a file's content (loads and task files)
    created_at   timestamptz,             -- when the original was made
    archived_at  timestamptz NOT NULL DEFAULT now(),
    run_id       bigint REFERENCES core.housekeeping_runs (id) ON DELETE SET NULL,
    UNIQUE (source_table, source_id)
);
CREATE INDEX archived_items_rule_idx ON core.archived_items (rule, archived_at DESC);
COMMENT ON TABLE core.archived_items IS 'Phase 35.1 (D371): what housekeeping archived; searchable on request';

-- the safe defaults (D371, D445): only archive, delete nothing until an admin says so; history is kept until a Super Admin
-- sets an age
INSERT INTO core.retention_rules (code, action, after_days) VALUES
    ('loads', 'archive', 90),
    ('task_files', 'archive', 90),
    ('notifications', 'archive', 365),
    ('history_versions', 'keep', 1095),        -- off until a Super Admin sets an age (D445)
    ('webhook_deliveries', 'keep', 365),
    ('discarded_changes', 'keep', 365),
    ('usage', 'keep', 730),
    ('housekeeping_runs', 'keep', 730)
ON CONFLICT (code) DO NOTHING;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.service_accounts, core.machine_credentials, core.usage_daily,
              core.retention_rules, core.housekeeping_runs, core.archived_items TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
END;
$$;
