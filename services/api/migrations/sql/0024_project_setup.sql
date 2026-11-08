-- =====================================================================================
-- 0024_project_setup: build phase 13.0.1 (version 0.14.2), setting up and running an architecture project (D274-D279)
--   * a project's scope (breadth, depth, time, domains), its sponsor and their asks, free notes (rich text), the model
--     its goals and outcomes live in (home_model), and how it ends: frozen, or merged into another project
--   * models are also referred to (read only), beside added, derived and created
--   * items: a placeholder (to deliver, no template yet), the templates chosen for it (empty: every one)
--   * viewpoints made for the project (own)
--   * sign-off of deliverables: requests and each signer's decision, with comments and evidence
-- Rows only: the rules are in eax/projects.py and eax/project_work.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.14.2', '0024_project_setup', 'Phase 13.0.1: project scope, goals and outcomes, sponsor, editing, sign-off, the landing page, finishing');

ALTER TABLE proj.projects
    ADD COLUMN scope_breadth  text NOT NULL DEFAULT '',          -- the enterprise, or the units and segments in scope
    ADD COLUMN scope_depth    text NOT NULL DEFAULT '',          -- strategic, segment or capability
    ADD COLUMN scope_domains  text[] NOT NULL DEFAULT '{}',      -- business, data, application, technology
    ADD COLUMN scope_start    date,
    ADD COLUMN scope_end      date,
    ADD COLUMN scope_horizon  text NOT NULL DEFAULT '',          -- the target state's time horizon, in words
    ADD COLUMN scope_notes    text NOT NULL DEFAULT '',
    ADD COLUMN sponsor_name   text NOT NULL DEFAULT '',
    ADD COLUMN sponsor_role   text NOT NULL DEFAULT '',
    ADD COLUMN sponsor_contact text NOT NULL DEFAULT '',
    ADD COLUMN sponsor_asks   jsonb NOT NULL DEFAULT '[]',        -- [{ask, by, measure}]
    ADD COLUMN notes_html     text NOT NULL DEFAULT '',          -- free notes, rich text (cleaned before it is stored)
    ADD COLUMN home_model     uuid,                              -- the model its goals and outcomes are entities in (D274)
    ADD COLUMN pending_goals  jsonb NOT NULL DEFAULT '[]',       -- goals waiting for the home model's metamodel copy
    ADD COLUMN finished_at    timestamptz,
    ADD COLUMN finished_by    text,
    ADD COLUMN finish_note    text NOT NULL DEFAULT '',
    ADD COLUMN merged_into    bigint REFERENCES proj.projects (id);
ALTER TABLE proj.projects DROP CONSTRAINT projects_status_check;
ALTER TABLE proj.projects ADD CONSTRAINT projects_status_check
    CHECK (status IN ('active', 'finishing', 'frozen', 'merged', 'closed'));

ALTER TABLE proj.project_models DROP CONSTRAINT project_models_how_check;
ALTER TABLE proj.project_models ADD CONSTRAINT project_models_how_check
    CHECK (how IN ('added', 'referred', 'derived', 'created'));

ALTER TABLE proj.items
    ADD COLUMN placeholder boolean NOT NULL DEFAULT false,      -- to be delivered; no template yet: built later
    ADD COLUMN templates   bigint[],                            -- the library templates chosen for it (NULL: every one)
    ADD COLUMN note        text NOT NULL DEFAULT '';

ALTER TABLE proj.project_viewpoints
    ADD COLUMN own boolean NOT NULL DEFAULT false;              -- made for this project (its code starts PV-)

ALTER TABLE proj.documents
    ADD COLUMN kind text CHECK (kind IN ('Deliverable', 'Artifact')),   -- NULL: the item's kind (a loose document: Artifact)
    ADD COLUMN signed_version integer;                                  -- the version that was signed off

-- sign-off of a deliverable's version (D276): raised by a contributor; every signer of its phase (or of the whole
-- project) decides; approved when all approve, rejected when one rejects
CREATE TABLE proj.signoff_requests (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    document_id bigint NOT NULL REFERENCES proj.documents (id) ON DELETE CASCADE,
    version     integer NOT NULL,
    signers     text[] NOT NULL,
    note        text NOT NULL DEFAULT '',
    state       text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'approved', 'rejected', 'withdrawn')),
    raised_by   text NOT NULL,
    raised_at   timestamptz NOT NULL DEFAULT now(),
    closed_at   timestamptz
);
CREATE INDEX signoff_requests_document ON proj.signoff_requests (document_id, state);

CREATE TABLE proj.signoff_decisions (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id  bigint NOT NULL REFERENCES proj.signoff_requests (id) ON DELETE CASCADE,
    signer      text NOT NULL,                                  -- whose decision it is
    decision    text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    how         text NOT NULL CHECK (how IN ('in-app', 'self', 'recorded')),   -- recorded: by someone else, with evidence
    comment     text NOT NULL DEFAULT '',
    recorded_by text NOT NULL,
    evidence_name text,
    evidence_mayan_id integer,
    at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (request_id, signer)
);

-- the new tables, like the rest of proj (0022)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;
