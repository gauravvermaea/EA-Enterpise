-- =====================================================================================
-- 0058_remote_instances: each person's remote EA Explorer instances and the recorded SSH sessions (R2.2, D634; owner,
--   10 Nov 2026 and 13 Nov 2026: the site picker lists a person's own instances; choosing one opens its own screens,
--   signed in its own way; a Super Admin may also open an SSH session to its host from the browser, every session
--   recorded; how a person proves who they are to the host is a configuration option, EAX_REMOTE_SSH_AUTH).
--   The list is personal data (the personal schema, R2.53); the sessions are the running of the installation (the
--   operations schema, R2.27). Tables and checks only (D248). No version change.
-- =====================================================================================

CREATE SCHEMA IF NOT EXISTS personal;
CREATE SCHEMA IF NOT EXISTS operations;

CREATE TABLE IF NOT EXISTS personal.remote_instances (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid        NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    username     text        NOT NULL CHECK (username = lower(username) AND username <> ''),
    name         text        NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 120),
    url          text        NOT NULL CHECK (url ~ '^https?://[^\s/]+' AND length(url) <= 500),
    note         text        NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
    ssh_host     text        NOT NULL DEFAULT '' CHECK (ssh_host ~ '^[A-Za-z0-9._:-]*$' AND length(ssh_host) <= 255),
    ssh_port     integer     NOT NULL DEFAULT 22 CHECK (ssh_port BETWEEN 1 AND 65535),
    ssh_user     text        NOT NULL DEFAULT '' CHECK (ssh_user ~ '^[A-Za-z0-9._-]*$' AND length(ssh_user) <= 64),
    ssh_key_enc  bytea,                               -- the private key, encrypted (EAX_REMOTE_SSH_AUTH=stored only)
    created_at   timestamptz NOT NULL DEFAULT now(),
    modified_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (username, name)
);
COMMENT ON TABLE personal.remote_instances IS 'R2.2: each person''s remote EA Explorer instances (the site picker)';

CREATE TABLE IF NOT EXISTS operations.ssh_sessions (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session     text        NOT NULL UNIQUE CHECK (session ~ '^[0-9a-f]{8,32}$'),
    username    text        NOT NULL,
    instance    text        NOT NULL DEFAULT '',
    host        text        NOT NULL,
    port        integer     NOT NULL,
    ssh_user    text        NOT NULL,
    auth        text        NOT NULL CHECK (auth IN ('ask', 'stored', 'server_key')),
    started_at  timestamptz NOT NULL DEFAULT now(),
    ended_at    timestamptz,
    reason      text        NOT NULL DEFAULT '',
    bytes       bigint      NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ssh_sessions_started ON operations.ssh_sessions (started_at DESC);
COMMENT ON TABLE operations.ssh_sessions IS 'R2.2: every SSH session opened from the browser; its transcript is work/ssh-sessions/<session>.log';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON personal.remote_instances, operations.ssh_sessions TO eax_app;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON personal.remote_instances, operations.ssh_sessions TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA personal TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA operations TO eax_migrator;
    END IF;
END;
$$;
