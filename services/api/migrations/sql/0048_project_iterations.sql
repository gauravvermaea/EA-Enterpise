-- =====================================================================================
-- 0048_project_iterations: version 0.19.0, ADM iteration types on projects (D571 to D574)
--   A project's current ADM cycle runs as one of TOGAF's iteration cycles (Full cycle, Architecture Capability,
--   Architecture Development, Transition Planning, Architecture Governance) or a custom set of phases; the phases it
--   leaves out are frozen (read only), never hidden or deleted. Every change is a row here, per cycle: the latest row of
--   the current cycle is the project's iteration; a cycle without a row runs as a Full cycle and the page asks.
-- Rows only: which phases are enabled is worked out in eax/iterations.py (no logic in the database, D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.19.0', '0048_project_iterations', 'ADM iteration types on projects')
ON CONFLICT (version) DO NOTHING;   -- several 0.19.0 migrations: the first one writes the version

CREATE TABLE IF NOT EXISTS proj.iteration_changes (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id          bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    cycle               integer NOT NULL DEFAULT 1,
    iteration           text NOT NULL,          -- full | capability | development | transition | governance | custom
    phases              text[] NOT NULL,        -- the enabled phases, P and A to H, in ADM order
    previous_iteration  text,                   -- NULL: none was chosen before (a Full cycle)
    previous_phases     text[],
    by_user             text NOT NULL,
    at                  timestamptz NOT NULL DEFAULT now(),
    note                text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS iteration_changes_project ON proj.iteration_changes (project_id, cycle, id DESC);
COMMENT ON TABLE proj.iteration_changes IS
    'A project''s ADM iteration per cycle, every change kept: who, when, from, to (D571-D574)';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;
