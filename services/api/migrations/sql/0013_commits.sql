-- =====================================================================================
-- 0013_commits: build phase 8 (version 0.8.3; built after 8.2, D161), commits, drafts, approvals and merges (D165)
--   * content (not the metamodel) is private to its author until committed (D165): every change waits
--     in a change set (core.change_sets, core.pending_changes); the core tables, the version history,
--     reports, graphs and MCP hold committed content only
--   * commits (core.commits, core.commit_items) keep what each change did, before and after, so a commit
--     can be rolled back, whole or item by item, as a new commit
--   * new model roles: Committer (commits changes) and History Viewer (sees everyone's commits, D151)
--   * draft models can be rejected (approval_state 'rejected', D165)
--   * merge sessions: a model uploaded into a model, its plan and decisions (D165)
-- The API decides who sees which change set (its author; the model's committers once requested).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.8.3', '0013_commits', 'Phase 8: commits of content, Committer and History Viewer roles, draft rejection, model merges');

-- ---------------------------------------------------------------- roles (D165, D151)
INSERT INTO core.app_roles (code, name, scope, description, sort_order) VALUES
    ('committer', 'Committer', 'model',
     'Commits content changes on this model: their own, and those others ask to commit; rejects, sends back and rolls back commits', 13),
    ('history-viewer', 'History Viewer', 'model',
     'Sees every person''s commits and changes on this model (D151); others see only their own', 15)
ON CONFLICT (code) DO NOTHING;
UPDATE core.app_roles SET sort_order = 14 WHERE code = 'architect';
UPDATE core.app_roles SET sort_order = 16 WHERE code = 'report-viewer';
UPDATE core.app_roles SET description = 'Owns this model: changes its metamodel, locks it, gives people roles on it, changes and commits its content, derives models from it'
 WHERE code = 'model-admin';
UPDATE core.app_roles SET description = 'The Model Admin''s deputy for content: changes this model''s content and commits it (theirs and others''); not the metamodel or people'
 WHERE code = 'model-sub-admin';
UPDATE core.app_roles SET description = 'Works on this model''s content: changes stay private until committed (by a Committer, or by themselves if they also commit)'
 WHERE code = 'architect';

-- A Committer changes content when committing (the database checks the person who writes): content is
-- theirs to change too. Replaces core.why_not of 0006.
CREATE OR REPLACE FUNCTION core.why_not(p_model bigint, p_part text) RETURNS text LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, core AS $$
DECLARE
    r    text[] := core.session_roles();
    mine text[];
BEGIN
    IF r IS NULL OR core.is_installer() OR 'super-admin' = ANY (r) THEN
        RETURN NULL;
    END IF;
    IF p_part = 'create' AND 'model-creator' = ANY (r) THEN
        RETURN NULL;
    END IF;
    mine := CASE WHEN p_model IS NULL THEN ARRAY[]::text[] ELSE core.model_roles(p_model) END;
    IF 'model-admin' = ANY (mine) AND p_part IN ('metamodel', 'content', 'model', 'people', 'create') THEN
        RETURN NULL;
    END IF;
    IF mine && ARRAY['architect', 'model-sub-admin', 'committer'] AND p_part = 'content' THEN
        RETURN NULL;
    END IF;
    RETURN CASE
        WHEN p_part = 'create' THEN 'creating a model needs the Model Creator role, or Model Admin on the model it comes from'
        WHEN cardinality(mine) = 0 THEN 'you have no role on this model (its Model Admin gives roles on its People tab)'
        WHEN p_part = 'content' THEN 'changing content needs the Architect, Committer, Model Sub Admin or Model Admin role on this model'
        WHEN p_part = 'people' THEN 'giving people roles on this model needs its Model Admin role'
        ELSE 'this needs the Model Admin role on this model' END;
END;
$$;

-- ---------------------------------------------------------------- change sets and their changes
CREATE TABLE core.change_sets (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id     bigint NOT NULL REFERENCES core.models (id),
    author       text NOT NULL,
    -- open: the author is working (only they see it); requested: waiting for a committer (the model's
    -- committers see it); returned: sent back to the author with a note; closed: nothing left pending
    status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'requested', 'returned', 'closed')),
    title        text NOT NULL DEFAULT '',
    request_note text NOT NULL DEFAULT '',
    reply_note   text NOT NULL DEFAULT '',
    requested_at timestamptz,
    replied_by   text,
    replied_at   timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    modified_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX change_sets_one_open_idx ON core.change_sets (model_id, author) WHERE status = 'open';
CREATE INDEX change_sets_model_idx ON core.change_sets (model_id, status);
COMMENT ON TABLE core.change_sets IS 'A person''s uncommitted content changes on a model (D165): private until they ask for a commit';

CREATE TABLE core.pending_changes (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid          uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    change_set_id bigint NOT NULL REFERENCES core.change_sets (id) ON DELETE CASCADE,
    model_id      bigint NOT NULL REFERENCES core.models (id),
    author        text NOT NULL,
    op            text NOT NULL CHECK (op IN ('entity.create', 'entity.update', 'entity.status', 'entity.delete', 'entity.rollback',
                                               'relationship.create', 'relationship.delete', 'relationship.rename')),
    args          jsonb NOT NULL,          -- what to do, replayed at commit (new entities and relationships carry their guid)
    base          jsonb,                   -- the committed state it was made against (to find conflicts at commit)
    mine          jsonb,                   -- the fields it changes, as they will be
    target        uuid,                    -- the entity or relationship it changes
    target_kind   text NOT NULL DEFAULT 'entity' CHECK (target_kind IN ('entity', 'relationship')),
    label         text NOT NULL DEFAULT '',
    status        text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'committed', 'rejected', 'discarded')),
    note          text NOT NULL DEFAULT '',
    warnings      jsonb NOT NULL DEFAULT '[]',   -- the rules the target fails with this change (shown before committing)
    commit_id     bigint,
    decided_by    text,
    decided_at    timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX pending_changes_model_idx ON core.pending_changes (model_id, status, author);
CREATE INDEX pending_changes_set_idx ON core.pending_changes (change_set_id, id);
CREATE INDEX pending_changes_target_idx ON core.pending_changes (target) WHERE status = 'pending';
COMMENT ON TABLE core.pending_changes IS 'One uncommitted content change, in the order made (D165); replayed when committed';

-- ---------------------------------------------------------------- commits
CREATE TABLE core.commits (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid          uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id      bigint NOT NULL REFERENCES core.models (id),
    number        integer NOT NULL,
    kind          text NOT NULL DEFAULT 'commit' CHECK (kind IN ('commit', 'rollback')),
    message       text NOT NULL DEFAULT '',
    committed_by  text NOT NULL,
    committed_at  timestamptz NOT NULL DEFAULT now(),
    authors       text[] NOT NULL DEFAULT '{}',
    rolls_back    bigint REFERENCES core.commits (id),
    UNIQUE (model_id, number)
);
CREATE INDEX commits_model_idx ON core.commits (model_id, committed_at DESC);
COMMENT ON TABLE core.commits IS 'Committed content changes (D165): what reached the model, by whom and from whose changes';

CREATE TABLE core.commit_items (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    commit_id      bigint NOT NULL REFERENCES core.commits (id) ON DELETE CASCADE,
    change_id      bigint REFERENCES core.pending_changes (id),
    author         text NOT NULL,
    op             text NOT NULL,
    args           jsonb NOT NULL DEFAULT '{}',
    target         uuid,
    target_kind    text NOT NULL DEFAULT 'entity',
    label          text NOT NULL DEFAULT '',
    before         jsonb,              -- the target before the item (to roll it back)
    after          jsonb,              -- the target after it (to see whether it changed since)
    rolled_back_by bigint REFERENCES core.commits (id)
);
CREATE INDEX commit_items_commit_idx ON core.commit_items (commit_id, id);
CREATE INDEX commit_items_target_idx ON core.commit_items (target);
ALTER TABLE core.pending_changes ADD CONSTRAINT pending_changes_commit_fk FOREIGN KEY (commit_id) REFERENCES core.commits (id);

-- ---------------------------------------------------------------- merges (D165)
CREATE TABLE core.merge_sessions (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id    bigint NOT NULL REFERENCES core.models (id),
    author      text NOT NULL,
    filename    text NOT NULL DEFAULT '',
    plan        jsonb NOT NULL,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'applied', 'cancelled')),
    result      jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    applied_at  timestamptz
);
CREATE INDEX merge_sessions_model_idx ON core.merge_sessions (model_id, author, status);
COMMENT ON TABLE core.merge_sessions IS 'A model uploaded to merge into a model (D165): the plan, the decisions, the change set it made';

-- ---------------------------------------------------------------- draft models can be rejected (D165)
ALTER TABLE core.models DROP CONSTRAINT IF EXISTS models_approval_state_check;
ALTER TABLE core.models ADD CONSTRAINT models_approval_state_check
    CHECK (approval_state IN ('', 'editing', 'requested', 'returned', 'rejected'));
ALTER TABLE core.model_publish_events DROP CONSTRAINT IF EXISTS model_publish_events_action_check;
ALTER TABLE core.model_publish_events ADD CONSTRAINT model_publish_events_action_check
    CHECK (action IN ('requested', 'approved', 'sent_back', 'request_withdrawn', 'rejected', 'reopened'));

-- an approver may also reject a requested draft (approval_state requested -> rejected): replaces
-- core.refuse_unpermitted of 0008 with 'rejected' let through the same door as 'returned'
CREATE OR REPLACE FUNCTION core.refuse_unpermitted() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_model bigint;
    v_part  text := TG_ARGV[0];
    v_why   text;
BEGIN
    IF core.session_roles() IS NULL THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    -- (separate statements: a row of core.models has no model_id field)
    IF TG_TABLE_NAME = 'models' THEN
        IF TG_OP = 'UPDATE' AND NEW.is_deleted AND NOT OLD.is_deleted
           AND NOT ('super-admin' = ANY (core.session_roles())) THEN
            RAISE EXCEPTION 'Not allowed for %: deleting a model needs the Super Admin role', core.current_actor()
                USING ERRCODE = 'insufficient_privilege', HINT = 'Archive it instead.';
        END IF;
        IF NEW.kind_code IN ('template', 'reference') AND core.may_curate_library() THEN
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;   -- the library's curator
        END IF;
        IF TG_OP = 'UPDATE' AND OLD.approval_state = 'requested' AND NEW.approval_state IN ('', 'returned', 'rejected')
           AND core.may_approve_draft(OLD.id, OLD.kind_code, OLD.source_model_id, OLD.parent_model_id) THEN
            RETURN NEW;   -- an approver approves (publishes), sends back or rejects a requested draft (D134, D165)
        END IF;
        IF TG_OP = 'INSERT' THEN
            -- a new model: judged on the model it comes from (Model Admins may derive from theirs)
            v_part := 'create';
            v_model := coalesce(NEW.parent_model_id, NEW.source_model_id);
            IF NEW.kind_code = 'reference' THEN
                RAISE EXCEPTION 'Not allowed for %: reference models are added to the library by a Library Admin',
                    core.current_actor() USING ERRCODE = 'insufficient_privilege';
            END IF;
            IF NEW.kind_code = 'template' AND 'model-creator' = ANY (core.session_roles()) THEN
                RETURN NEW;   -- Model Creators build roots (MOD-016)
            END IF;
        ELSE
            v_model := CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END;
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        v_model := OLD.model_id;
    ELSE
        v_model := NEW.model_id;
    END IF;
    v_why := core.why_not(v_model, v_part);
    IF v_why IS NOT NULL AND TG_TABLE_NAME = 'model_users' AND TG_OP = 'INSERT' THEN
        -- (nested: NEW.role exists only on model_users rows)
        IF NEW.role = 'model-admin' AND NEW.username = lower(core.current_actor())
           AND core.first_role_by_creator(NEW.model_id) THEN
            v_why := NULL;   -- whoever created a model (allowed above) may make themselves its first Model Admin
        END IF;
    END IF;
    IF v_why IS NOT NULL THEN
        RAISE EXCEPTION 'Not allowed for %: %', core.current_actor(), v_why
            USING ERRCODE = 'insufficient_privilege',
                  HINT = 'Global roles are given in Keycloak; roles on a model on the model''s People tab.';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;
