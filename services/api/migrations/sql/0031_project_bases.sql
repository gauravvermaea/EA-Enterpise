-- =====================================================================================
-- 0031_project_bases: build phase 13.1 (version 0.15.0), project bases and governance (D303 to D307)
--   * project bases, a hierarchy like the models': Empty project › TOGAF 10 project › Organisation base › every
--     project; the first two read-only for everyone, the Organisation base changed by Super Admins
--   * what a base holds is offered down to the projects below it (taken or skipped); principles and standards
--     marked mandatory cannot be changed or removed below
--   * standards (business, data, application, technology, security, and groups of one's own) beside principles
--   * a governance log per project (decisions, dispensations, compliance assessments, risks, issues and kinds of
--     one's own), an architecture charter per project, skills of the people on a project
-- Rows only: the rules are in eax/project_bases.py and eax/governance.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.15.0', '0031_project_bases', 'Phase 13.1: project bases, standards, governance log, charter');

ALTER TABLE proj.projects
    ADD COLUMN base_kind text NOT NULL DEFAULT '' CHECK (base_kind IN ('', 'empty', 'togaf', 'org')),
    ADD COLUMN base_id   bigint REFERENCES proj.projects (id);          -- the base (or library project) it derives from

-- principles and steps keep where they came from in the base (to offer changes down) and whether they are mandatory
ALTER TABLE proj.principles
    ADD COLUMN guid uuid NOT NULL DEFAULT gen_random_uuid(),
    ADD COLUMN origin_guid uuid,
    ADD COLUMN mandatory boolean NOT NULL DEFAULT false,
    ADD COLUMN sort_order integer NOT NULL DEFAULT 0;
ALTER TABLE proj.steps
    ADD COLUMN guid uuid NOT NULL DEFAULT gen_random_uuid(),
    ADD COLUMN origin_guid uuid;

CREATE TABLE proj.standards (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    area        text NOT NULL DEFAULT '',                  -- Business, Data, Application, Technology, Security, or one's own
    name        text NOT NULL,
    description text NOT NULL DEFAULT '',                  -- rich text
    status      text NOT NULL DEFAULT 'Active',            -- Trial, Active, Deprecated, Obsolete
    source      text NOT NULL DEFAULT '',                  -- who publishes it
    mandatory   boolean NOT NULL DEFAULT false,
    origin_guid uuid,                                      -- the base's standard it came from
    sort_order  integer NOT NULL DEFAULT 0,
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_by text,
    modified_at timestamptz
);
CREATE INDEX standards_project ON proj.standards (project_id, area, sort_order);

-- what a project chose not to take from its base (it is not offered again)
CREATE TABLE proj.base_skips (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('principle', 'standard', 'step')),
    origin_guid uuid NOT NULL,
    skipped_by  text NOT NULL,
    skipped_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, kind, origin_guid)
);

CREATE TABLE proj.gov_records (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    kind        text NOT NULL,                             -- Decision, Dispensation, ... or a kind of the project's own
    ref         text NOT NULL DEFAULT '',                  -- DEC-001
    title       text NOT NULL,
    html        text NOT NULL DEFAULT '',
    status      text NOT NULL DEFAULT '',
    owner       text NOT NULL DEFAULT '',
    raised_on   date NOT NULL DEFAULT current_date,
    expires_on  date,                                      -- a dispensation's end, a risk's review date
    principle   uuid,                                      -- the principle or standard it is about (a dispensation)
    standard    uuid,
    related     text NOT NULL DEFAULT '',
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_by text,
    modified_at timestamptz
);
CREATE INDEX gov_records_project ON proj.gov_records (project_id, kind, raised_on DESC);

CREATE TABLE proj.gov_kinds (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    name        text NOT NULL,
    prefix      text NOT NULL DEFAULT '',
    statuses    text[] NOT NULL DEFAULT '{}',
    sort_order  integer NOT NULL DEFAULT 0,
    added_by    text NOT NULL,
    PRIMARY KEY (project_id, name)
);

CREATE TABLE proj.charters (
    project_id  bigint PRIMARY KEY REFERENCES proj.projects (id) ON DELETE CASCADE,
    sections    jsonb NOT NULL DEFAULT '{}',               -- section key -> rich text
    state       text NOT NULL DEFAULT 'Draft' CHECK (state IN ('Draft', 'Approved')),
    approved_by text,
    approved_at timestamptz,
    modified_by text,
    modified_at timestamptz
);

ALTER TABLE proj.org_people ADD COLUMN skills text[] NOT NULL DEFAULT '{}';

-- a phase marked complete (owner, 8 Nov 2026): completion counts phases only; reopened at any time (the row goes)
CREATE TABLE proj.phase_states (
    project_id   bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    cycle        integer NOT NULL DEFAULT 1,
    phase        text NOT NULL,
    completed_by text NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT now(),
    note         text NOT NULL DEFAULT '',
    PRIMARY KEY (project_id, cycle, phase)
);

-- a project marked complete (owner, 8 Nov 2026): at any time, and reopened at any time (apart from finishing it)
ALTER TABLE proj.projects ADD COLUMN completed_at timestamptz, ADD COLUMN completed_by text;

-- documents (owner, 8 Nov 2026): a document's name apart from its file's name; a document may be made with no file yet
-- (its file is added later); a document is a deliverable, an artifact, or neither
ALTER TABLE proj.documents ADD COLUMN title text NOT NULL DEFAULT '';
ALTER TABLE proj.documents DROP CONSTRAINT IF EXISTS documents_kind_check;
ALTER TABLE proj.documents ADD CONSTRAINT documents_kind_check CHECK (kind IN ('Deliverable', 'Artifact', 'None'));

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;
