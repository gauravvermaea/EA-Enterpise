-- =====================================================================================
-- 0040_mcp_activity: version 0.18.0, MCP (phases 26 and 27, D368, D458, D459, D482 to D489)
--   * the AI activity log: every MCP call, per person: the tool, a summary of the question, the result size, what it
--     changed; the person sees their own, Super Admins and IT Admins see everyone's
--   * MCP previews: a tool that changes something first returns a preview and a confirm token; the change is made
--     only when the same tool is called again with that token, by the same person, with the same arguments (D458)
-- Rows only: the rules are in eax/mcp_activity.py and eax/mcp_ops.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.18.0', '0040_mcp_activity', 'Batch 2 and 3 (D421): MCP activity log and previews')
ON CONFLICT (version) DO NOTHING;   -- several 0.18.0 migrations: the first one writes the version

CREATE TABLE core.mcp_activity (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at           timestamptz NOT NULL DEFAULT now(),
    username     text NOT NULL CHECK (username = lower(username) AND username <> ''),
    tool         text NOT NULL,
    kind         text NOT NULL CHECK (kind IN ('read', 'preview', 'change', 'refused', 'error')),
    summary      text NOT NULL DEFAULT '',          -- the question, as the assistant put it (why), or the arguments shortened
    arguments    jsonb NOT NULL DEFAULT '{}',       -- shortened: long texts and lists cut
    result_size  integer NOT NULL DEFAULT 0,        -- characters of the answer
    changes      jsonb NOT NULL DEFAULT '[]',       -- what it changed: [{what, model, link}]
    model        text NOT NULL DEFAULT '',          -- the model (or project) it was about, as given
    credential   text NOT NULL DEFAULT '',          -- the machine credential's name, when not a sign-in
    ms           integer NOT NULL DEFAULT 0,
    error        text NOT NULL DEFAULT ''
);
CREATE INDEX mcp_activity_user_idx ON core.mcp_activity (username, at DESC);
CREATE INDEX mcp_activity_at_idx ON core.mcp_activity (at DESC);
COMMENT ON TABLE core.mcp_activity IS 'Phases 26/27 (D368, D482): every MCP call per person: tool, question, result size, changes';

CREATE TABLE core.mcp_previews (
    token        text PRIMARY KEY,
    username     text NOT NULL,
    tool         text NOT NULL,
    args_hash    text NOT NULL,                     -- SHA-256 of the arguments (confirm and why left out)
    summary      jsonb NOT NULL DEFAULT '{}',
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL,
    used_at      timestamptz
);
CREATE INDEX mcp_previews_user_idx ON core.mcp_previews (username, created_at DESC);
COMMENT ON TABLE core.mcp_previews IS 'D458: a change through MCP is previewed first and made only with the preview''s confirm token';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.mcp_activity, core.mcp_previews TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
END;
$$;
