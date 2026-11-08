-- =====================================================================================
-- 0025_project_templates: build phase 13.0.3 (version 0.14.3), model roles and project templates (D281, D282)
--   * a model's role in a project: current state, target state, transition state (numbered), scenario, reference,
--     working copy
--   * project templates: specialised wizards with the decisions already taken, kept as data (14 shipped; a Super Admin
--     changes them or saves a project as a new one); a project remembers the template it came from
-- Rows only: the rules are in eax/project_templates.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.14.3', '0025_project_templates', 'Phase 13.0.3: model roles in a project and project templates as wizards');

ALTER TABLE proj.project_models
    ADD COLUMN role text CHECK (role IN ('current', 'target', 'transition', 'scenario', 'reference', 'working-copy')),
    ADD COLUMN role_seq integer;                                 -- transition 1, 2, ... (and scenario A, B as 1, 2)

CREATE TABLE proj.project_templates (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        text NOT NULL UNIQUE CHECK (code ~ '^[a-z0-9-]{2,60}$'),
    name        text NOT NULL,
    icon        text NOT NULL DEFAULT '',
    description text NOT NULL DEFAULT '',
    spec        jsonb NOT NULL DEFAULT '{}',                     -- the decisions taken: models by role, purpose, scope, phases, viewpoints...
    builtin     boolean NOT NULL DEFAULT false,
    retired     boolean NOT NULL DEFAULT false,
    sort_order  integer NOT NULL DEFAULT 1000,
    created_by  text NOT NULL DEFAULT 'system',
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_by text NOT NULL DEFAULT 'system',
    modified_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE proj.projects ADD COLUMN template_code text;        -- the template it was made from (none: the full wizard)

-- the new tables, like the rest of proj (0022)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;
