-- =====================================================================================
-- 0018_notifications: build phase 8.1 (version 0.11.0), actions, alerts and workflows (D84, D86, D209)
--   * core.notifications and core.notification_recipients: what happened, to whom; those that need action stay open
--     until resolved with a note (once for all who received them), information ones are read or dismissed by each person
--   * core.requests and core.request_comments: tickets between two people (subject, body; open, in progress, done or
--     declined), private to the two
--   * core.webhooks and core.webhook_deliveries: installation-wide webhooks (IT and Super Admins), signed plain JSON,
--     retried with back-off; never email (D209)
--   * core.metamodel_version_changes: the changes each metamodel version was made of, so a version can be pushed down
--   * core.metamodel_pushes and core.metamodel_push_targets: a parent's metamodel versions pushed to the models directly
--     under it, forced or offered, accepted or rejected by each child's Model Admin (D84)
--   * core.change_documents: a page listing every change accepted into a model (pushed metamodel versions, commits,
--     merges), linked from a notification to everyone on the model (WF-018)
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.11.0', '0018_notifications', 'Phase 8.1: notifications, requests, webhooks, metamodel push-down, change documents');

-- ---------------------------------------------------------------- notifications
CREATE TABLE core.notifications (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid          uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    kind          text NOT NULL,                  -- e.g. commit.requested, metamodel.offered, request.new, model.locked
    category      text NOT NULL CHECK (category IN ('commit', 'metamodel', 'request', 'model', 'system')),
    needs_action  boolean NOT NULL DEFAULT false, -- stays open until resolved with a note
    model_id      bigint REFERENCES core.models (id) ON DELETE CASCADE,
    title         text NOT NULL CHECK (btrim(title) <> ''),
    body          text NOT NULL DEFAULT '',
    link          text NOT NULL DEFAULT '',       -- where to act or read: a screen of the web app (#/...)
    ref_kind      text NOT NULL DEFAULT '',       -- what it is about: request, push_target, change_set, change_document
    ref_id        bigint,
    actor         text NOT NULL,                  -- who made it happen
    -- a model's notification: Super Admins have a role on every model (global), so they get it too, added to their
    -- recipients when they next look (notify.join_super_admin)
    to_super_admins boolean NOT NULL DEFAULT false,
    created_at    timestamptz NOT NULL DEFAULT now(),
    resolved_at   timestamptz,                    -- action notifications only
    resolved_by   text,
    resolution    text NOT NULL DEFAULT '',
    CHECK (needs_action OR resolved_at IS NULL)
);
CREATE INDEX notifications_model_idx ON core.notifications (model_id, created_at DESC);
CREATE INDEX notifications_ref_idx ON core.notifications (ref_kind, ref_id) WHERE ref_id IS NOT NULL;
COMMENT ON TABLE core.notifications IS 'Phase 8.1: what happened and who must know (D209); action ones are resolved once for all';

CREATE TABLE core.notification_recipients (
    notification_id bigint NOT NULL REFERENCES core.notifications (id) ON DELETE CASCADE,
    username        text NOT NULL CHECK (username = lower(username) AND username <> ''),
    read_at         timestamptz,
    dismissed_at    timestamptz,                  -- information notifications: put away by this person
    PRIMARY KEY (notification_id, username)
);
CREATE INDEX notification_recipients_user_idx ON core.notification_recipients (username, notification_id DESC);

-- ---------------------------------------------------------------- requests (tickets between two people)
CREATE TABLE core.requests (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    number      integer GENERATED ALWAYS AS IDENTITY (START WITH 1001) UNIQUE,
    subject     text NOT NULL CHECK (btrim(subject) <> '' AND length(subject) <= 200),
    body        text NOT NULL DEFAULT '' CHECK (length(body) <= 20000),
    sender      text NOT NULL CHECK (sender = lower(sender)),
    receiver    text NOT NULL CHECK (receiver = lower(receiver)),
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'done', 'declined')),
    close_note  text NOT NULL DEFAULT '',          -- done and declined need one
    via         text NOT NULL DEFAULT 'screen' CHECK (via IN ('screen', 'api', 'mcp')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    closed_at   timestamptz,
    -- a request to oneself is a note (owner, 6 Nov 2026)
    CHECK (status NOT IN ('done', 'declined') OR (btrim(close_note) <> '' AND closed_at IS NOT NULL))
);
CREATE INDEX requests_receiver_idx ON core.requests (receiver, status, updated_at DESC);
CREATE INDEX requests_sender_idx ON core.requests (sender, status, updated_at DESC);
COMMENT ON TABLE core.requests IS 'Phase 8.1: a request from one person to another, like a ticket (D209); private to the two';

CREATE TABLE core.request_comments (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id  bigint NOT NULL REFERENCES core.requests (id) ON DELETE CASCADE,
    author      text NOT NULL,
    body        text NOT NULL CHECK (btrim(body) <> '' AND length(body) <= 20000),
    -- a status change is kept in the trail too (status set, body = the note or "Started")
    status      text CHECK (status IS NULL OR status IN ('open', 'in_progress', 'done', 'declined')),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX request_comments_request_idx ON core.request_comments (request_id, id);

-- ---------------------------------------------------------------- webhooks (installation-wide)
CREATE TABLE core.webhooks (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    name        text NOT NULL CHECK (btrim(name) <> ''),
    url         text NOT NULL CHECK (url ~* '^https?://'),
    secret      text NOT NULL,                  -- signs each message (HMAC-SHA256 in the X-EAX-Signature header)
    kinds       text[] NOT NULL DEFAULT '{}',   -- the categories it receives (commit, metamodel, request, model); empty: all
    enabled     boolean NOT NULL DEFAULT true,
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.webhooks IS 'Phase 8.1: installation-wide webhooks set by IT and Super Admins (D209)';

CREATE TABLE core.webhook_deliveries (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    webhook_id      bigint NOT NULL REFERENCES core.webhooks (id) ON DELETE CASCADE,
    notification_id bigint REFERENCES core.notifications (id) ON DELETE SET NULL,
    payload         jsonb NOT NULL,
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
    attempts        integer NOT NULL DEFAULT 0,
    next_at         timestamptz NOT NULL DEFAULT now(),
    last_status     integer,
    last_error      text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    sent_at         timestamptz
);
CREATE INDEX webhook_deliveries_due_idx ON core.webhook_deliveries (next_at) WHERE status = 'pending';
CREATE INDEX webhook_deliveries_hook_idx ON core.webhook_deliveries (webhook_id, id DESC);

-- ---------------------------------------------------------------- metamodel push-down (D84)
-- the changes a metamodel version was made of (the editor and the grids), in order, with what each made: replayed on
-- the models below when the version is pushed. A version made another way (a draft applied, a package) has none and
-- cannot be pushed.
CREATE TABLE core.metamodel_version_changes (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id  bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    version   integer NOT NULL,
    seq       integer NOT NULL,
    op        text NOT NULL,
    payload   jsonb NOT NULL DEFAULT '{}',
    result    jsonb NOT NULL DEFAULT '{}',
    note      text NOT NULL DEFAULT '',
    UNIQUE (model_id, version, seq)
);

CREATE TABLE core.metamodel_pushes (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid           uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    from_model_id  bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    versions       integer[] NOT NULL,             -- the parent's versions in the package, in order
    mode           text NOT NULL CHECK (mode IN ('forced', 'offered')),
    fill_defaults  boolean NOT NULL DEFAULT true,  -- new attributes with a default: fill existing entities with it
    note           text NOT NULL DEFAULT '',
    came_from      bigint REFERENCES core.metamodel_pushes (id),   -- passed on from the level above
    pushed_by      text NOT NULL,
    pushed_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX metamodel_pushes_from_idx ON core.metamodel_pushes (from_model_id, pushed_at DESC);

CREATE TABLE core.metamodel_push_targets (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    push_id         bigint NOT NULL REFERENCES core.metamodel_pushes (id) ON DELETE CASCADE,
    model_id        bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    -- offered: waiting for the child's Model Admin; applied: forced or accepted and made; rejected: the child diverges;
    -- failed: could not be applied (the error says why); skipped: a read-only model
    status          text NOT NULL DEFAULT 'offered' CHECK (status IN ('offered', 'applied', 'rejected', 'failed', 'skipped')),
    decided_by      text,
    decided_at      timestamptz,
    note            text NOT NULL DEFAULT '',
    error           text NOT NULL DEFAULT '',
    applied_version integer,                       -- the child's own version the package became
    UNIQUE (push_id, model_id)
);
CREATE INDEX metamodel_push_targets_model_idx ON core.metamodel_push_targets (model_id, status);
COMMENT ON TABLE core.metamodel_push_targets IS 'Phase 8.1: what each model under the parent did with a pushed metamodel package (D84); rejected = diverged';

-- the versions of a model already pushed down (or made by an arriving push), so the next push carries only what is new
CREATE VIEW core.metamodel_versions_pushed AS
SELECT p.from_model_id AS model_id, unnest(p.versions) AS version FROM core.metamodel_pushes p;

-- A package forced down from the parent is made with the parent's authority (D84): core.why_not lets the metamodel of
-- the one model the API names in eax.push_down change for that statement (set and cleared around the change only)
CREATE OR REPLACE FUNCTION core.why_not(p_model bigint, p_part text) RETURNS text LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, core AS $$
DECLARE
    r    text[] := core.session_roles();
    mine text[];
BEGIN
    IF r IS NULL OR core.is_installer() OR 'super-admin' = ANY (r) THEN
        RETURN NULL;
    END IF;
    -- a metamodel package pushed down from the parent (D84, phase 8.1): forced by the parent's Model Admin, or accepted
    -- by this model's; the API sets eax.push_down to this model for the length of that one change, after its own checks
    -- (the model row too: a new metamodel version bumps its version number)
    IF p_part IN ('metamodel', 'model') AND p_model IS NOT NULL
       AND coalesce(current_setting('eax.push_down', true), '') = p_model::text THEN
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

-- ---------------------------------------------------------------- change documents (WF-018)
CREATE TABLE core.change_documents (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id    bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('metamodel', 'commit', 'merge')),
    title       text NOT NULL,
    summary     text NOT NULL DEFAULT '',
    body        jsonb NOT NULL DEFAULT '{}',       -- sections of changes: {sections: [{title, rows: [{what, item, old, new, note}]}]}
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX change_documents_model_idx ON core.change_documents (model_id, created_at DESC);
COMMENT ON TABLE core.change_documents IS 'Phase 8.1: a page listing every change accepted into a model, for everyone on it (D86, WF-018)';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT ON core.notifications, core.notification_recipients, core.requests, core.request_comments,
                        core.webhooks, core.webhook_deliveries, core.metamodel_version_changes, core.metamodel_pushes,
                        core.metamodel_push_targets, core.change_documents, core.metamodel_versions_pushed TO eax_migrator;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        -- private between people (requests) or operational: never in reports
        REVOKE ALL ON core.notifications, core.notification_recipients, core.requests, core.request_comments,
                      core.webhooks, core.webhook_deliveries FROM eax_report;
    END IF;
END;
$$;
