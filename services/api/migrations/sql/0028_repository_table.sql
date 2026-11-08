-- =====================================================================================
-- 0028_repository_table: build phase 13.0.6 (version 0.14.6), the project repository as a table (D290)
--   * your own version label on each document, given at every check-out and check-in, beside the system version
--   * tags on documents (free text, any number), to find and group them
--   * a document accepted directly, with evidence (a note and an optional file), beside approval by the sign-off people
--   * a quorum per project: approved when that many of the sign-off people approve; any rejection rejects
--   * archived and deleted documents (all their versions), shown only when asked for and not loaded otherwise
--   * "won't need this" on a document class (an item), with the reason, who and when (anyone on the project)
-- Rows only: the rules are in eax/projects.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.14.6', '0028_repository_table', 'Phase 13.0.6: the project repository as a table (your version, not needed)');

ALTER TABLE proj.documents
    ADD COLUMN user_version text NOT NULL DEFAULT '',          -- the version as the person calls it (0.3 draft, 1.0 for approval)
    ADD COLUMN out_version  text NOT NULL DEFAULT '',          -- the label given when it was checked out (optional)
    ADD COLUMN tags         text[] NOT NULL DEFAULT '{}',      -- the document's tags (D290)
    ADD COLUMN accepted_by  text,                              -- accepted directly (not by the sign-off people)
    ADD COLUMN accepted_at  timestamptz,
    ADD COLUMN accepted_note text NOT NULL DEFAULT '',         -- the evidence: why it is accepted
    ADD COLUMN accepted_evidence text NOT NULL DEFAULT '',     -- the evidence file, kept in 00_Project/Sign-off evidence
    ADD COLUMN archived_by  text,
    ADD COLUMN archived_at  timestamptz,
    ADD COLUMN deleted_by   text,
    ADD COLUMN deleted_at   timestamptz;

ALTER TABLE proj.documents DROP CONSTRAINT documents_state_check,
    ADD CONSTRAINT documents_state_check CHECK (state IN ('Draft', 'In review', 'Approved', 'Accepted', 'Rejected', 'Superseded',
                                                          'Withdrawn', 'Not for use'));
CREATE INDEX documents_live ON proj.documents (project_id) WHERE archived_at IS NULL AND deleted_at IS NULL;

ALTER TABLE proj.projects
    ADD COLUMN signoff_quorum integer CHECK (signoff_quorum IS NULL OR signoff_quorum >= 1);   -- NULL: a majority

ALTER TABLE proj.signoff_requests
    ADD COLUMN quorum integer;                                 -- how many approvals it needs, fixed when it is raised

-- more about the sponsor and about the goals, in rich text (owner, 7 Nov 2026)
ALTER TABLE proj.projects
    ADD COLUMN sponsor_notes_html text NOT NULL DEFAULT '',
    ADD COLUMN goals_notes_html   text NOT NULL DEFAULT '';

-- steps added at any time, and repeated (owner, 7 Nov 2026): each completion is a sub step of the same name under the
-- step, with who did it and when; "+ sub step" opens another, to complete later
ALTER TABLE proj.steps
    ADD COLUMN parent_step_id bigint REFERENCES proj.steps (id) ON DELETE CASCADE,
    ADD COLUMN added_by       text,
    ADD COLUMN added_at       timestamptz,
    ADD COLUMN due_date       date;
CREATE INDEX steps_parent ON proj.steps (parent_step_id) WHERE parent_step_id IS NOT NULL;

-- the repository build (owner's laptop, 7 Nov 2026): when the build started (a build left "building" by a restart is
-- taken up again after 15 minutes; two runners never build one project at once), and whether an item's cabinet was
-- filed as in use (its "(not_for_use)" suffix is put right when that changes)
ALTER TABLE proj.projects ADD COLUMN repo_started_at timestamptz;
-- asked again while a build ran: built again when it finishes (review, 7 Nov 2026)
ALTER TABLE proj.projects ADD COLUMN repo_again boolean NOT NULL DEFAULT false;
ALTER TABLE proj.items ADD COLUMN mayan_cabinet_chosen boolean;

-- the phase a project shows a viewpoint with (empty: its usual one)
ALTER TABLE proj.project_viewpoints ADD COLUMN phase text;

-- a model made from another model as it was at one of its tags (a separate copy, never a child)
ALTER TABLE core.models
    ADD COLUMN source_tag_id   uuid,
    ADD COLUMN source_tag_name text NOT NULL DEFAULT '';

ALTER TABLE proj.document_events
    ADD COLUMN user_version text NOT NULL DEFAULT '';

ALTER TABLE proj.items
    ADD COLUMN not_needed_reason text NOT NULL DEFAULT '',
    ADD COLUMN not_needed_by     text,
    ADD COLUMN not_needed_at     timestamptz,
    ADD COLUMN added_by          text;                         -- a class added from the repository (NULL: the set-up)

-- ---------------------------------------------------------------- the stakeholder matrix (owner, 8 Nov 2026, D294)
-- TOGAF's stakeholder management: each stakeholder of the project (typed in: a person or a group), its category, power
-- and interest (High/Medium/Low; the class is worked out from them in the application, and may be set by hand), its
-- position (ability to disrupt, understanding and commitment now and needed, support needed), concerns and the
-- viewpoints and document classes that answer them, how it is engaged, contact details and notes; and any number of
-- dated discussion notes.
CREATE TABLE proj.stakeholders (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid                 uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id           bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    sort_order           integer NOT NULL DEFAULT 0,
    name                 text NOT NULL,
    organisation         text NOT NULL DEFAULT '',
    role_title           text NOT NULL DEFAULT '',
    category             text NOT NULL DEFAULT '',
    email                text NOT NULL DEFAULT '',
    phone                text NOT NULL DEFAULT '',
    concerns             text NOT NULL DEFAULT '',
    power                text NOT NULL DEFAULT '' CHECK (power IN ('', 'H', 'M', 'L')),
    interest             text NOT NULL DEFAULT '' CHECK (interest IN ('', 'H', 'M', 'L')),
    class                text NOT NULL DEFAULT '' CHECK (class IN ('', 'key', 'satisfied', 'informed', 'minimal')),
    disrupt              text NOT NULL DEFAULT '' CHECK (disrupt IN ('', 'H', 'M', 'L')),
    understanding_now    text NOT NULL DEFAULT '' CHECK (understanding_now IN ('', 'H', 'M', 'L')),
    understanding_needed text NOT NULL DEFAULT '' CHECK (understanding_needed IN ('', 'H', 'M', 'L')),
    commitment_now       text NOT NULL DEFAULT '' CHECK (commitment_now IN ('', 'H', 'M', 'L')),
    commitment_needed    text NOT NULL DEFAULT '' CHECK (commitment_needed IN ('', 'H', 'M', 'L')),
    support_needed       text NOT NULL DEFAULT '' CHECK (support_needed IN ('', 'H', 'M', 'L')),
    approach             text NOT NULL DEFAULT '',
    frequency            text NOT NULL DEFAULT '',
    channel              text NOT NULL DEFAULT '',
    owner                text NOT NULL DEFAULT '',
    next_contact         date,
    notes_html           text NOT NULL DEFAULT '',
    viewpoints           text[] NOT NULL DEFAULT '{}',
    items                bigint[] NOT NULL DEFAULT '{}',
    created_by           text NOT NULL,
    created_at           timestamptz NOT NULL DEFAULT now(),
    modified_by          text,
    modified_at          timestamptz
);
CREATE INDEX stakeholders_project ON proj.stakeholders (project_id, sort_order);

CREATE TABLE proj.stakeholder_notes (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid           uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    stakeholder_id bigint NOT NULL REFERENCES proj.stakeholders (id) ON DELETE CASCADE,
    held_on        date NOT NULL DEFAULT current_date,
    title          text NOT NULL DEFAULT '',
    html           text NOT NULL DEFAULT '',
    by_user        text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    modified_at    timestamptz
);
CREATE INDEX stakeholder_notes_of ON proj.stakeholder_notes (stakeholder_id, held_on DESC);

-- ---------------------------------------------------------------- tasks (owner, 8 Nov 2026, D298)
-- A project's scratchpad of what people are doing: no dates, not project management. A task may belong to a step or a
-- sub step; finishing a task never finishes its step. Everyone on the project sees every task.
CREATE TABLE proj.tasks (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id   bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    step_id      bigint REFERENCES proj.steps (id) ON DELETE SET NULL,
    title        text NOT NULL,
    notes_html   text NOT NULL DEFAULT '',
    status       text NOT NULL DEFAULT 'Created',
    assigned_to  text NOT NULL DEFAULT '',
    created_by   text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    modified_by  text,
    modified_at  timestamptz
);
CREATE INDEX tasks_project ON proj.tasks (project_id, status);
-- a project's own task statuses, after the standard ones
CREATE TABLE proj.task_statuses (
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    name        text NOT NULL,
    sort_order  integer NOT NULL DEFAULT 0,
    added_by    text NOT NULL,
    PRIMARY KEY (project_id, name)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;

-- ---------------------------------------------------------------- links and the reference area (owner, 8 Nov 2026, D296)
-- A link is an entry of the repository with no file: an external web address, or another project's document or
-- document class (shown as it is there now). It is filed like a document (a class, or a folder), tagged, marked D or A,
-- accepted or signed off; it has no check-out and no versions. The Reference area is TOGAF's Reference Library
-- (05_Reference_Library), opened up: folders of any shape, documents and links.
ALTER TABLE proj.documents
    ADD COLUMN link_url      text NOT NULL DEFAULT '',
    ADD COLUMN link_project  uuid,
    ADD COLUMN link_document uuid,
    ADD COLUMN link_item     uuid,
    ADD COLUMN description   text NOT NULL DEFAULT '';
-- a library project: its reference material is offered to new projects (Super Admins mark it)
ALTER TABLE proj.projects ADD COLUMN is_library boolean NOT NULL DEFAULT false;

-- a project's principles by area (Business, Data, Application, Technology, Security...; owner, 8 Nov 2026)
ALTER TABLE proj.principles ADD COLUMN area text NOT NULL DEFAULT '';

-- a person pins projects as well as models on Architecture work (owner, 8 Nov 2026)
ALTER TABLE core.favourites DROP CONSTRAINT favourites_kind_check;
ALTER TABLE core.favourites ADD CONSTRAINT favourites_kind_check CHECK (kind IN ('entity', 'model', 'view', 'project'));
