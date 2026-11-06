-- =====================================================================================
-- 0022_projects: build phase 13 (version 0.14.0), architecture projects and their repository (D258 to D264)
--   * the project library (schema proj, lib_*): purposes, ADM phases, steps, deliverables and artifacts (each with every
--     source it came from), the master folders and principles; seeded from eax/seed/project_library.json and kept by
--     Super Admins
--   * template libraries (D264): EA Explorer's own, TOGAF 10 (files loaded once, kept exactly as published) and the
--     organisation's own; the setup a Super Admin finishes before the first project
--   * architecture projects: purpose, parent (a rerun of the ADM), the ADM cycle, its people (Project Admin, Lead
--     Architect, Architects, Model Admin, Model Sub Admin, Stakeholders), sign-off people, models, viewpoints,
--     principles, steps (accepted or removed with the reason), deliverables and artifacts (chosen, or not_for_use)
--   * the project repository: its folders and documents, stored in Mayan (cabinets, documents, versions,
--     check-out); these tables keep the link, who checked out what, and the state
-- Rows only: who may do what is decided in eax/projects.py (no logic in the database, D248). No foreign key and no
-- query crosses from proj into the other schemas, so proj can move to a database of its own (EAX_PROJECTS_DB_URL, D266).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.14.0', '0022_projects', 'Phase 13: architecture projects, the project library, the project wizard, the repository in Mayan');

CREATE SCHEMA IF NOT EXISTS proj;

-- ---------------------------------------------------------------- the library (Super Admins)
CREATE TABLE proj.lib_purposes (
    code        text PRIMARY KEY,
    name        text NOT NULL,
    standard    boolean NOT NULL DEFAULT false,
    sort_order  integer NOT NULL DEFAULT 100,
    retired     boolean NOT NULL DEFAULT false
);

CREATE TABLE proj.lib_phases (
    code        text PRIMARY KEY,                -- P, A, B, C, C-D, C-A, D, E, F, G, H, RM, X
    name        text NOT NULL,
    workspace   text NOT NULL,                   -- 09_ADM_Phase_Workspaces/<...>
    objectives  text NOT NULL DEFAULT '',
    inputs      text NOT NULL DEFAULT '',
    sort_order  integer NOT NULL
);

CREATE TABLE proj.lib_steps (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    phase       text NOT NULL REFERENCES proj.lib_phases (code),
    seq         integer NOT NULL,
    name        text NOT NULL,
    source      text NOT NULL,                   -- TOGAF 10, Meridian framework, or whoever added it
    marking     text NOT NULL DEFAULT '',        -- the Meridian framework's Kept / Modified / Added
    note        text NOT NULL DEFAULT '',
    retired     boolean NOT NULL DEFAULT false,
    UNIQUE (phase, name)
);

CREATE TABLE proj.lib_items (
    id           text PRIMARY KEY,               -- G001 ...: one deliverable or artifact, however many sources name it
    phase        text NOT NULL REFERENCES proj.lib_phases (code),
    name         text NOT NULL,
    kind         text NOT NULL CHECK (kind IN ('Deliverable', 'Artifact')),
    type         text NOT NULL DEFAULT '',       -- Document, Catalog, Matrix, Diagram...
    default_pick boolean NOT NULL DEFAULT true,  -- offered ticked in the wizard; unticked items go in as not_for_use
    work_folder  text NOT NULL,                  -- its folder in the phase workspace
    approved_folder text NOT NULL DEFAULT '',    -- the repository class it moves to when approved
    templates    text NOT NULL DEFAULT '',
    retired      boolean NOT NULL DEFAULT false
);

CREATE TABLE proj.lib_item_sources (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id     text NOT NULL REFERENCES proj.lib_items (id) ON DELETE CASCADE,
    source      text NOT NULL,                   -- TOGAF 10, TOGAF 10 template, Meridian framework, Meridian repository, Phase-wise deliverables
    phase       text NOT NULL DEFAULT '',
    name        text NOT NULL,
    kind        text NOT NULL DEFAULT '',
    type        text NOT NULL DEFAULT '',
    marking     text NOT NULL DEFAULT '',
    note        text NOT NULL DEFAULT '',
    files       text NOT NULL DEFAULT '',
    location    text NOT NULL DEFAULT ''
);

CREATE TABLE proj.lib_folders (
    path        text PRIMARY KEY,
    holds       text NOT NULL DEFAULT '',
    togaf_class text NOT NULL DEFAULT '',
    origin      text NOT NULL DEFAULT '',
    retired     boolean NOT NULL DEFAULT false
);

CREATE TABLE proj.lib_principles (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        text NOT NULL UNIQUE,
    set_name    text NOT NULL DEFAULT '',        -- Architecture, Security...
    category    text NOT NULL DEFAULT '',
    name        text NOT NULL,
    statement   text NOT NULL DEFAULT '',
    rationale   text NOT NULL DEFAULT '',
    implications text NOT NULL DEFAULT '',
    tier        text NOT NULL DEFAULT '',
    owner       text NOT NULL DEFAULT '',
    measure     text NOT NULL DEFAULT '',
    source      text NOT NULL DEFAULT '',
    retired     boolean NOT NULL DEFAULT false
);

-- ---------------------------------------------------------------- projects
CREATE TABLE proj.projects (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    name        text NOT NULL UNIQUE,
    purpose     text NOT NULL,                   -- a lib_purposes code or the user's own words
    description text NOT NULL DEFAULT '',
    parent_id   bigint REFERENCES proj.projects (id),   -- a rerun of the ADM on an existing project
    cycle       integer NOT NULL DEFAULT 1,      -- the TOGAF ADM cycle the project is in
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    repo_state  text NOT NULL DEFAULT 'pending' CHECK (repo_state IN ('pending', 'building', 'ready', 'failed')),
    repo_note   text NOT NULL DEFAULT '',
    repo_tries  integer NOT NULL DEFAULT 0,
    mayan_cabinet_id integer,
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE proj.members (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    username    text NOT NULL,
    role        text NOT NULL CHECK (role IN ('project-admin', 'lead-architect', 'architect', 'model-admin', 'model-sub-admin', 'stakeholder')),
    added_by    text NOT NULL,
    added_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, username, role)
);

-- who signs off documents: one set for the whole project (phase ''), or a set per phase
CREATE TABLE proj.signoff (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    phase       text NOT NULL DEFAULT '',
    username    text NOT NULL,
    PRIMARY KEY (project_id, phase, username)
);

CREATE TABLE proj.project_models (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    model_guid  uuid NOT NULL,                   -- the model's guid (no foreign key: proj may move to its own database, D266)
    how         text NOT NULL CHECK (how IN ('added', 'derived', 'created')),
    added_by    text NOT NULL,
    added_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, model_guid)
);

CREATE TABLE proj.project_viewpoints (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    viewpoint   text NOT NULL,                   -- a viewpoint's code (VP-01 ...)
    PRIMARY KEY (project_id, viewpoint)
);

CREATE TABLE proj.principles (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    code        text NOT NULL DEFAULT '',
    name        text NOT NULL,
    statement   text NOT NULL DEFAULT '',
    rationale   text NOT NULL DEFAULT '',
    implications text NOT NULL DEFAULT '',
    library_id  bigint REFERENCES proj.lib_principles (id),
    inherited_from bigint REFERENCES proj.projects (id),   -- a child inherits its parent's principles
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE proj.steps (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    cycle       integer NOT NULL DEFAULT 1,
    phase       text NOT NULL,
    seq         integer NOT NULL,
    name        text NOT NULL,
    library_id  bigint REFERENCES proj.lib_steps (id),     -- NULL: the project's own step
    removed     boolean NOT NULL DEFAULT false,            -- a removed standard step stays, shown crossed out
    removed_reason text NOT NULL DEFAULT '',
    done_at     timestamptz,                               -- marked done by a contributor; reopened by the Lead Architect or Project Admin
    done_by     text,
    done_note   text NOT NULL DEFAULT ''
);
CREATE INDEX steps_project ON proj.steps (project_id, cycle, phase, seq);

CREATE TABLE proj.items (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    cycle       integer NOT NULL DEFAULT 1,
    phase       text NOT NULL,
    name        text NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('Deliverable', 'Artifact')),
    type        text NOT NULL DEFAULT '',
    library_id  text REFERENCES proj.lib_items (id),       -- NULL: the project's own item
    chosen      boolean NOT NULL DEFAULT true,             -- false: put in its folder as not_for_use (it can be chosen later)
    folder      text NOT NULL,
    approved_folder text NOT NULL DEFAULT '',
    mayan_cabinet_id integer
);
CREATE INDEX items_project ON proj.items (project_id, cycle, phase);

CREATE TABLE proj.folders (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    path        text NOT NULL,
    mayan_cabinet_id integer,
    PRIMARY KEY (project_id, path)
);

-- a document in the repository: the file and its versions are in Mayan
CREATE TABLE proj.documents (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    item_id     bigint REFERENCES proj.items (id) ON DELETE SET NULL,
    folder      text NOT NULL,
    mayan_document_id integer,
    file_name   text NOT NULL,
    versions    integer NOT NULL DEFAULT 1,
    origin      text NOT NULL DEFAULT 'upload',   -- upload, template, generated
    state       text NOT NULL DEFAULT 'Draft' CHECK (state IN ('Draft', 'In review', 'Approved', 'Rejected', 'Superseded', 'Withdrawn', 'Not for use')),
    checked_out_by text,
    checked_out_at timestamptz,
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_by text NOT NULL,
    modified_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX documents_project ON proj.documents (project_id, item_id);

-- what happened to a document (uploaded, checked out, checked in, undone...): who, when, which version
CREATE TABLE proj.document_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES proj.documents (id) ON DELETE CASCADE,
    at          timestamptz NOT NULL DEFAULT now(),
    by_user     text NOT NULL,
    action      text NOT NULL,
    version     integer,
    note        text NOT NULL DEFAULT ''
);

-- ---------------------------------------------------------------- template libraries (D264)
-- Named sets of templates: EA Explorer's own (shipped, files read from its folder), TOGAF 10 (The Open Group's files,
-- loaded once by a Super Admin, never shipped) and the organisation's own (a zip uploaded in the library's folder
-- layout). One added in a project's wizard is private to whoever added it (then to that project) until a Super Admin
-- shares it with every project.
CREATE TABLE proj.template_libraries (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    name        text NOT NULL UNIQUE,
    kind        text NOT NULL CHECK (kind IN ('ea-explorer', 'togaf', 'own')),
    description text NOT NULL DEFAULT '',
    shared      boolean NOT NULL DEFAULT false,
    project_id  bigint REFERENCES proj.projects (id) ON DELETE SET NULL,
    state       text NOT NULL DEFAULT 'ready' CHECK (state IN ('loading', 'ready', 'failed')),
    note        text NOT NULL DEFAULT '',
    created_by  text NOT NULL DEFAULT 'system',
    created_at  timestamptz NOT NULL DEFAULT now(),
    shared_by   text NOT NULL DEFAULT '',
    shared_at   timestamptz
);

-- a template of a library: for an item (deliverable or artifact) or for a folder; the file is in Mayan, or (EA Explorer's)
-- in its folder in the release
CREATE TABLE proj.lib_templates (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    library_id  bigint NOT NULL REFERENCES proj.template_libraries (id) ON DELETE CASCADE,
    path        text NOT NULL,                   -- where it sits in the library's folder layout
    item_id     text REFERENCES proj.lib_items (id),
    source      text NOT NULL DEFAULT '',
    code        text NOT NULL DEFAULT '',
    name        text NOT NULL,
    phase       text NOT NULL DEFAULT '',
    purpose     text NOT NULL DEFAULT '',
    produced_by text NOT NULL DEFAULT '',
    approved_by text NOT NULL DEFAULT '',
    when_used   text NOT NULL DEFAULT '',
    fields      integer,
    folder      text NOT NULL DEFAULT '',
    origin      text NOT NULL DEFAULT '',        -- Sample, rebranded / Starter / Uploaded
    mayan_document_id integer,
    file_name   text NOT NULL DEFAULT '',
    uploaded_by text NOT NULL DEFAULT '',
    uploaded_at timestamptz,
    UNIQUE (library_id, path)
);

-- a library zip waiting to be stored in Mayan by the background job (removed once loaded)
CREATE TABLE proj.template_library_uploads (
    library_id  bigint PRIMARY KEY REFERENCES proj.template_libraries (id) ON DELETE CASCADE,
    content     bytea NOT NULL,
    uploaded_by text NOT NULL,
    uploaded_at timestamptz NOT NULL DEFAULT now()
);

-- the libraries a project takes its templates from (all their templates for an item are copied in)
CREATE TABLE proj.project_libraries (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    library_id  bigint NOT NULL REFERENCES proj.template_libraries (id),
    sort_order  integer NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, library_id)
);

-- the template library setup a Super Admin finishes before the first project (one row once done)
CREATE TABLE proj.template_setup (
    id          integer PRIMARY KEY CHECK (id = 1),
    done_by     text NOT NULL,
    done_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON SCHEMA proj IS 'Architecture projects and their repository (phase 13, D258 to D262); files in Mayan';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT USAGE ON SCHEMA proj TO eax_migrator;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;
