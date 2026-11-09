-- =====================================================================================
-- 0032_repository_tags: version 0.15.1, the project's documents table (owner, 8 Nov 2026, D312)
--   * a tag on the whole repository: the version of every document at that moment, to download them all as they
--     were, or to bring the repository back to the tag (a tag "before application of tag <name>" is made first)
--   * templates added to a document class to download (apart from the ones its documents were made from)
--   * the template a document was copied from
--   * the dates each step was opened and closed, and its history
--   * the project's own placement of entity types and entities in the content framework
--   * key questions and the viewpoints (or placeholder viewpoints) that answer them
--   * Business Model Canvases: current, target, working copies and scenarios, compared and cleaned up
-- Rows only: the rules are in eax/repo_tags.py and eax/projects.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.15.1', '0032_repository_tags', 'Repository tags; templates added to a document class');

CREATE TABLE proj.repo_tags (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    name        text NOT NULL,
    note        text NOT NULL DEFAULT '',
    auto        boolean NOT NULL DEFAULT false,     -- made by a revert: "before application of tag <name>"
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, name)
);

-- each document at the tag: its version then, and whether it was archived then
CREATE TABLE proj.repo_tag_docs (
    tag_id       bigint NOT NULL REFERENCES proj.repo_tags (id) ON DELETE CASCADE,
    document_id  bigint NOT NULL REFERENCES proj.documents (id) ON DELETE CASCADE,
    version      integer NOT NULL,
    user_version text NOT NULL DEFAULT '',
    file_name    text NOT NULL DEFAULT '',
    title        text NOT NULL DEFAULT '',
    archived     boolean NOT NULL DEFAULT false,
    PRIMARY KEY (tag_id, document_id)
);

ALTER TABLE proj.items ADD COLUMN offered_templates bigint[] NOT NULL DEFAULT '{}';

-- the template a document was copied from: the repository build copies each template once, whatever the copy's file is
-- called after a check-in (review, 8 Nov 2026)
ALTER TABLE proj.documents ADD COLUMN template_id bigint;

-- steps: when each was opened and closed (owner, 8 Nov 2026). A step made with the project opened when the project was
-- made; every closing, reopening and opening is kept in the step's history
ALTER TABLE proj.steps ALTER COLUMN added_at SET DEFAULT now();
UPDATE proj.steps s SET added_at = p.created_at FROM proj.projects p WHERE p.id = s.project_id AND s.added_at IS NULL;
CREATE TABLE proj.step_events (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    step_id  bigint NOT NULL REFERENCES proj.steps (id) ON DELETE CASCADE,
    at       timestamptz NOT NULL DEFAULT now(),
    by_user  text NOT NULL,
    action   text NOT NULL CHECK (action IN ('opened', 'closed', 'reopened')),
    note     text NOT NULL DEFAULT ''
);
CREATE INDEX step_events_step ON proj.step_events (step_id, at);

-- tagging in the content framework, per project (owner, 8 Nov 2026): who placed a document class or a document, and
-- the project's own placement of its models' entity types and entities (over the metamodel's default; other projects
-- are not affected). Areas are content framework codes joined by commas, as everywhere (D309)
ALTER TABLE proj.items ADD COLUMN area_set_by text, ADD COLUMN area_set_at timestamptz;
ALTER TABLE proj.documents ADD COLUMN area_set_by text, ADD COLUMN area_set_at timestamptz;
CREATE TABLE proj.cf_type_areas (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    type_guid   uuid NOT NULL,                  -- core.entity_types.guid of one of the project's models
    areas       text NOT NULL,
    set_by      text NOT NULL,
    set_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, type_guid)
);
CREATE TABLE proj.cf_entity_areas (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    entity_guid uuid NOT NULL,                  -- core.entities.guid
    areas       text NOT NULL,
    set_by      text NOT NULL,
    set_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, entity_guid)
);
-- defaults set by admins (owner, 8 Nov 2026, D317): built-in, then the admin's (a deliverable or artifact in the project
-- library, a template's own areas over its class's, an entity type in its metamodel, an entity in its model), then a
-- parent project's, then the project's own. The project's placement of an entity type keeps the type's code too, so a
-- project based on it inherits the placement for the same type in its own models.
ALTER TABLE proj.lib_templates ADD COLUMN content_area text NOT NULL DEFAULT '';
ALTER TABLE core.entities ADD COLUMN content_area text NOT NULL DEFAULT '';
ALTER TABLE proj.cf_type_areas ADD COLUMN type_code text NOT NULL DEFAULT '';
-- the Repository Area (D318): the part of the Architecture Repository an entity type or a document class is filed in,
-- one value on the type or the class (not on each entity or document); empty: the built-in default
ALTER TABLE core.entity_types ADD COLUMN repository_area text NOT NULL DEFAULT '';
ALTER TABLE proj.lib_items ADD COLUMN repository_area text NOT NULL DEFAULT '';
-- approval of governance records (owner, 8 Nov 2026, D321): every record has an approval state beside its own status.
-- Sent for approval to the project's sign-off people (approved when the project's quorum approves; any rejection
-- rejects it), or approved directly by anyone who contributes with evidence (a file) or a reason. A change to an
-- approved record makes it a draft again; each approval, rejection and change is kept in its history.
ALTER TABLE proj.gov_records ADD COLUMN approval text NOT NULL DEFAULT 'Draft'
        CHECK (approval IN ('Draft', 'Waiting for approval', 'Approved', 'Rejected')),
    ADD COLUMN approved_by text, ADD COLUMN approved_at timestamptz, ADD COLUMN approval_note text NOT NULL DEFAULT '',
    ADD COLUMN evidence_name text, ADD COLUMN evidence_mayan_id integer;
CREATE TABLE proj.gov_approvals (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    record_id   bigint NOT NULL REFERENCES proj.gov_records (id) ON DELETE CASCADE,
    signers     text[] NOT NULL,
    quorum      integer NOT NULL,
    note        text NOT NULL DEFAULT '',
    state       text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'approved', 'rejected', 'withdrawn')),
    raised_by   text NOT NULL,
    raised_at   timestamptz NOT NULL DEFAULT now(),
    closed_at   timestamptz
);
CREATE INDEX gov_approvals_record ON proj.gov_approvals (record_id, state);
CREATE TABLE proj.gov_decisions (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    approval_id bigint NOT NULL REFERENCES proj.gov_approvals (id) ON DELETE CASCADE,
    signer      text NOT NULL,
    decision    text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    comment     text NOT NULL DEFAULT '',
    at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (approval_id, signer)
);
CREATE TABLE proj.gov_history (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    record_id   bigint NOT NULL REFERENCES proj.gov_records (id) ON DELETE CASCADE,
    at          timestamptz NOT NULL DEFAULT now(),
    by_user     text NOT NULL,
    action      text NOT NULL,                  -- logged, changed, sent for approval, approved, rejected, approved with evidence...
    note        text NOT NULL DEFAULT '',
    snapshot    jsonb                           -- the record as it was (the approved version is kept when it changes)
);
CREATE INDEX gov_history_record ON proj.gov_history (record_id, at);
-- the Architecture Repository (owner, 8 Nov 2026, phase 13.0.9, D324): calendars, the Architecture Board's members.
-- A calendar event belongs to a project (project_id) or to the organisation (NULL): a date, a time, a topic, once or
-- repeated (daily, weekly on chosen weekdays, monthly, yearly; until a date or a number of times); skipped dates kept.
CREATE TABLE proj.cal_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    project_id  bigint REFERENCES proj.projects (id) ON DELETE CASCADE,       -- NULL: the organisation's calendar
    topic       text NOT NULL,
    starts_on   date NOT NULL,
    at_time     time,                                                         -- NULL: all day
    minutes     integer NOT NULL DEFAULT 60,
    notes       text NOT NULL DEFAULT '',
    repeat      text NOT NULL DEFAULT 'none' CHECK (repeat IN ('none', 'daily', 'weekly', 'monthly', 'yearly')),
    weekdays    integer[] NOT NULL DEFAULT '{}',                              -- weekly: 0 Monday .. 6 Sunday
    until_on    date,
    times       integer,
    skipped     date[] NOT NULL DEFAULT '{}',
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_by text,
    modified_at timestamptz
);
CREATE INDEX cal_events_project ON proj.cal_events (project_id, starts_on);
-- a private subscription link per person and calendar ('org', or a project's guid): renewed to stop the old one
CREATE TABLE proj.cal_feeds (
    username    text NOT NULL,
    calendar    text NOT NULL,
    token       text NOT NULL UNIQUE,
    every       boolean NOT NULL DEFAULT false,         -- made by an admin who sees every project
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (username, calendar)
);
-- the reference library's fixed top folders, beside the model library's root and reference models (D324)
INSERT INTO proj.org_ref_folders (path, description, added_by) VALUES
    ('Foundation architectures', 'Generic building blocks, services and standards every architecture builds on', 'system'),
    ('Common systems architectures', 'Architectures of common systems (security, management, network) reused across the organisation', 'system'),
    ('Industry architectures', 'Architectures and reference models of an industry', 'system'),
    ('Organisation''s own architectures', 'The organisation''s own reference architectures and patterns', 'system')
ON CONFLICT (path) DO NOTHING;
-- tracking sheets (owner, 8 Nov 2026, phase 13.2, D325): light sheets with no schema rules, at project level
-- (project_id) and organisation level (NULL); every value text; the columns are whatever was uploaded or added
CREATE TABLE proj.sheets (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    project_id  bigint REFERENCES proj.projects (id) ON DELETE CASCADE,
    name        text NOT NULL,
    description text NOT NULL DEFAULT '',
    columns     text[] NOT NULL DEFAULT '{}',
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_by text,
    modified_at timestamptz
);
CREATE TABLE proj.sheet_rows (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sheet_id    bigint NOT NULL REFERENCES proj.sheets (id) ON DELETE CASCADE,
    seq         integer NOT NULL,
    cells       jsonb NOT NULL DEFAULT '{}'                     -- column name -> text
);
CREATE INDEX sheet_rows_sheet ON proj.sheet_rows (sheet_id, seq);
-- principles (owner, 8 Nov 2026, D327): the organisation's set lives in the Organisation base, each enforced (mandatory
-- below it) or optional (a project may take it out); a principle may refine a higher-level one (refines: the guid of
-- the principle it refines, in the same project or the base it came from); areas may be added before they have principles
ALTER TABLE proj.principles ADD COLUMN refines uuid;
CREATE TABLE proj.principle_areas (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    name        text NOT NULL,
    sort_order  integer NOT NULL DEFAULT 0,
    added_by    text NOT NULL,
    PRIMARY KEY (project_id, name)
);
CREATE TABLE proj.board_members (
    username    text PRIMARY KEY,
    role        text NOT NULL DEFAULT '',
    added_by    text NOT NULL,
    added_at    timestamptz NOT NULL DEFAULT now()
);

-- key questions (owner, 9 Nov 2026): the stakeholder questions the project's work answers, what we expect the answer or
-- the approach to be, and the viewpoints that answer each one (many to many: a question may need several viewpoints, a
-- viewpoint may answer several questions). A placeholder viewpoint stands in where no viewpoint fits: a text, or an
-- empty file (docx, pptx...) in the project's files; it stays in the project (never in the organisation's viewpoints)
CREATE TABLE proj.key_questions (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    sort_order  integer NOT NULL DEFAULT 0,
    question    text NOT NULL,
    asked_by    text NOT NULL DEFAULT '',                  -- the stakeholder(s) asking, as written
    approach    text NOT NULL DEFAULT '',                  -- the answer we expect, or how we will answer it
    -- open, then answered (by a contributor), then accepted by the stakeholder (in the application, or recorded by a
    -- contributor with optional evidence); a rejection sends it back to open (history in question_events)
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'answered', 'accepted')),
    answer      text NOT NULL DEFAULT '',
    answered_by text NOT NULL DEFAULT '',
    answered_at timestamptz,
    accepted_by text NOT NULL DEFAULT '',                  -- the stakeholder: a user name, or a name as recorded
    accepted_at timestamptz,
    accept_note text NOT NULL DEFAULT '',
    accept_recorded_by text NOT NULL DEFAULT '',           -- the contributor who recorded it (empty: accepted in the application)
    evidence_document_id bigint REFERENCES proj.documents (id) ON DELETE SET NULL,
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    changed_by  text NOT NULL DEFAULT '',
    changed_at  timestamptz
);
CREATE TABLE proj.placeholder_viewpoints (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    code        text NOT NULL,                             -- PH-01 ... within the project
    name        text NOT NULL,
    description text NOT NULL DEFAULT '',
    kind        text NOT NULL DEFAULT 'text' CHECK (kind IN ('text', 'file')),
    file_type   text NOT NULL DEFAULT '',                  -- a file placeholder: docx, pptx, xlsx, pdf, drawio, md, txt
    document_id bigint REFERENCES proj.documents (id) ON DELETE SET NULL,   -- its file in the project's files, once made
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, code)
);
-- what an answer points to (owner, 9 Nov 2026: "a summary of the answer pointing to artifacts with links"): a document in
-- the project's repository, or a link (a page, a report, a shared file); the viewpoints mapped to the question link too
CREATE TABLE proj.question_links (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_id bigint NOT NULL REFERENCES proj.key_questions (id) ON DELETE CASCADE,
    document_id bigint REFERENCES proj.documents (id) ON DELETE CASCADE,
    url         text NOT NULL DEFAULT '',
    label       text NOT NULL DEFAULT '',
    sort_order  integer NOT NULL DEFAULT 0,
    added_by    text NOT NULL,
    added_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE proj.question_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_id bigint NOT NULL REFERENCES proj.key_questions (id) ON DELETE CASCADE,
    action      text NOT NULL,                             -- asked, changed, answered, accepted, rejected, reopened ...
    status      text NOT NULL DEFAULT '',                  -- the status after it
    username    text NOT NULL,
    at          timestamptz NOT NULL DEFAULT now(),
    note        text NOT NULL DEFAULT ''
);
CREATE INDEX question_events_question ON proj.question_events (question_id, at);
CREATE TABLE proj.question_viewpoints (
    question_id bigint NOT NULL REFERENCES proj.key_questions (id) ON DELETE CASCADE,
    viewpoint   text NOT NULL,                             -- a viewpoint's code (VP-, PV-) or a placeholder's (PH-)
    PRIMARY KEY (question_id, viewpoint)
);

-- Business Model Canvases (owner, 9 Nov 2026): first-class in a project, free-standing from the models. A project has
-- any number: current state, target state, working copies and scenarios, each draft or agreed. Items keep a lineage
-- (the same item across copies), so two canvases compare (added, changed, removed). In a working copy changes are
-- marked by hand (added green, changed amber with the old text, removed crossed out in red) until a clean canvas is
-- made from it
CREATE TABLE proj.canvases (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    name        text NOT NULL,
    kind        text NOT NULL DEFAULT 'current' CHECK (kind IN ('current', 'target', 'working', 'scenario')),
    status      text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'agreed')),
    description text NOT NULL DEFAULT '',
    source_id   bigint REFERENCES proj.canvases (id) ON DELETE SET NULL,     -- the canvas it was made from
    source_note text NOT NULL DEFAULT '',                                     -- how: a copy, cleaned up, a comparison
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    changed_by  text NOT NULL DEFAULT '',
    changed_at  timestamptz
);
CREATE TABLE proj.canvas_items (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    canvas_id   bigint NOT NULL REFERENCES proj.canvases (id) ON DELETE CASCADE,
    block       text NOT NULL CHECK (block IN ('key_partners', 'key_activities', 'key_resources', 'value_propositions',
                                               'customer_relationships', 'channels', 'customer_segments', 'cost_structure',
                                               'revenue_streams')),
    sort_order  integer NOT NULL DEFAULT 0,
    text        text NOT NULL,
    note        text NOT NULL DEFAULT '',
    lineage     uuid NOT NULL DEFAULT gen_random_uuid(),   -- the same item in every copy of the canvas
    mark        text NOT NULL DEFAULT '' CHECK (mark IN ('', 'added', 'changed', 'removed')),   -- a working copy's marks
    was_text    text NOT NULL DEFAULT '',                  -- changed: the text before
    changed_by  text NOT NULL DEFAULT '',
    changed_at  timestamptz
);
CREATE INDEX canvas_items_canvas ON proj.canvas_items (canvas_id, block, sort_order);
-- the documents behind a canvas (what was used to build it): uploaded with it, or a document of the project
CREATE TABLE proj.canvas_documents (
    canvas_id   bigint NOT NULL REFERENCES proj.canvases (id) ON DELETE CASCADE,
    document_id bigint NOT NULL REFERENCES proj.documents (id) ON DELETE CASCADE,
    note        text NOT NULL DEFAULT '',
    added_by    text NOT NULL,
    added_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (canvas_id, document_id)
);
CREATE TABLE proj.canvas_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canvas_id   bigint NOT NULL REFERENCES proj.canvases (id) ON DELETE CASCADE,
    action      text NOT NULL,
    username    text NOT NULL,
    at          timestamptz NOT NULL DEFAULT now(),
    note        text NOT NULL DEFAULT ''
);

-- each user's own skills (owner, 9 Nov 2026, D353): free tags people add to themselves on their profile; the Skills
-- repository lists every EA Explorer user (from Keycloak) with them. Tags typed against users on projects' Organisation
-- tabs before this are moved onto the users once.
CREATE TABLE proj.user_skills (
    username    text PRIMARY KEY,
    skills      text[] NOT NULL DEFAULT '{}',
    modified_by text NOT NULL,
    modified_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO proj.user_skills (username, skills, modified_by)
SELECT lower(o.username), array_agg(DISTINCT k ORDER BY k), 'migration 0032'
  FROM proj.org_people o, unnest(o.skills) AS k
 WHERE o.username <> '' AND k <> ''
 GROUP BY lower(o.username)
ON CONFLICT (username) DO NOTHING;

-- the TOGAF business architecture viewpoints (owner, 9 Nov 2026, D345): the form a viewpoint opens in (catalog, matrix,
-- diagram, heat, rels; empty: diagram) and the TOGAF artifact it gives
ALTER TABLE core.viewpoints
    ADD COLUMN default_view   text NOT NULL DEFAULT '',
    ADD COLUMN togaf_artifact text NOT NULL DEFAULT '';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;
