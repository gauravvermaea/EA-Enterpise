-- =====================================================================================
-- 0020_quality: build phase 12 (version 0.13.0), validation and data quality (D239)
--   * quality settings per model: the stale period (one for every type), when quality is measured on a schedule, and the
--     completeness weights (per entity type and item); a model takes what its ancestors set and may change it
--   * quality rules without SQL: must have a relationship, attribute conditions, cross-entity consistency, naming and
--     uniqueness; each an error (blocks a commit) or a warning; set on a metamodel, inherited down the hierarchy
--   * a Model Admin's change to settings or rules waits for a Super Admin's approval (core.quality_changes)
--   * quality runs: each measurement kept with its date, scores by type and owner, and its findings (the trend)
--   * quality seals: an owner attests an entity is correct, or a Model Admin marks it still current; a seal expires after
--     the stale period, and an edit by someone else breaks it at once
--   * what was already told to whom (reminders as it happens, without repeating them)
-- Who may read and change these is decided in eax/quality.py: anyone who reads a model reads its quality.
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.13.0', '0020_quality', 'Phase 12: validation and data quality: settings, weights, rules, approvals, runs, seals');

-- ---------------------------------------------------------------- weights in the metamodel (D241)
-- Each attribute has a default data quality weight where it is defined, and an entity type may override it where the
-- attribute is added to the type. NULL: the default (3 for a required attribute, 1 for another). 0 leaves it out.
ALTER TABLE core.attribute_types ADD COLUMN quality_weight smallint CHECK (quality_weight IS NULL OR quality_weight BETWEEN 0 AND 10);
ALTER TABLE core.item_attributes ADD COLUMN quality_weight smallint CHECK (quality_weight IS NULL OR quality_weight BETWEEN 0 AND 10);
COMMENT ON COLUMN core.attribute_types.quality_weight IS 'Data quality weight by default (0-10; NULL: 3 required, 1 other), D241';
COMMENT ON COLUMN core.item_attributes.quality_weight IS 'Data quality weight on this type (0-10; NULL: the attribute''s), D241';

-- ---------------------------------------------------------------- settings and weights (inherited)
CREATE TABLE core.quality_settings (
    model_id    bigint PRIMARY KEY REFERENCES core.models (id) ON DELETE CASCADE,
    stale_days  integer CHECK (stale_days IS NULL OR stale_days BETWEEN 7 AND 3650),   -- NULL: as the parent says
    cron        text CHECK (cron IS NULL OR cron ~ '^\S+ \S+ \S+ \S+ \S+$'),            -- scheduled measurement; NULL: as the parent
    weights     jsonb NOT NULL DEFAULT '{}',   -- {"<EntityTypeCode or *>": {"attr:<Code>" | "rel:any" | "rel:<TypeCode>" |
                                               --   "field:description": weight 0..10}}; a model's own override its parents'
    score_parts jsonb CHECK (score_parts IS NULL OR jsonb_typeof(score_parts) = 'object'),
                                               -- the score's weights {"completeness", "rules", "freshness"} adding up to 100
                                               -- (D244); NULL: as the parent says
    bands       jsonb CHECK (bands IS NULL OR jsonb_typeof(bands) = 'object'),
                                               -- the colours {"green": from, "amber": from}, red below (D244); NULL: inherit
    modified_by text NOT NULL DEFAULT core.current_actor(),
    modified_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.quality_settings IS 'A model''s own quality settings (D239); what it does not set comes from its ancestors';

-- ---------------------------------------------------------------- rules without SQL (inherited)
CREATE TABLE core.quality_rules (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id    bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    code        text NOT NULL CHECK (code ~ '^[A-Z]{1,4}-[0-9A-Za-z-]{1,20}$'),   -- QR-01; a child's rule with the same
                                                                                   -- code replaces (or switches off) its parent's
    name        text NOT NULL CHECK (btrim(name) <> ''),
    kind        text NOT NULL CHECK (kind IN ('relationship', 'attribute', 'consistency', 'naming')),
    entity_type text NOT NULL,                     -- the entity type code the rule is about
    spec        jsonb NOT NULL DEFAULT '{}',        -- what it checks (eax/quality.py RULE_KINDS)
    severity    text NOT NULL DEFAULT 'warning' CHECK (severity IN ('error', 'warning')),
    enabled     boolean NOT NULL DEFAULT true,
    message     text NOT NULL DEFAULT '',
    created_by  text NOT NULL DEFAULT core.current_actor(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_by text NOT NULL DEFAULT core.current_actor(),
    modified_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (model_id, code)
);
COMMENT ON TABLE core.quality_rules IS 'Data quality rules without SQL (D239): error (blocks a commit) or warning';

-- ---------------------------------------------------------------- a Model Admin's change waits for a Super Admin
CREATE TABLE core.quality_changes (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid          uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id      bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    kind          text NOT NULL CHECK (kind IN ('settings', 'rule', 'rule.delete')),
    payload       jsonb NOT NULL,
    summary       text NOT NULL DEFAULT '',
    note          text NOT NULL DEFAULT '',
    requested_by  text NOT NULL,
    requested_at  timestamptz NOT NULL DEFAULT now(),
    status        text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'withdrawn')),
    decided_by    text,
    decided_at    timestamptz,
    decision_note text NOT NULL DEFAULT ''
);
CREATE INDEX quality_changes_pending_idx ON core.quality_changes (model_id) WHERE status = 'pending';
COMMENT ON TABLE core.quality_changes IS 'Quality settings and rules a Model Admin changed, waiting for a Super Admin (D239)';

-- ---------------------------------------------------------------- measurements (kept with their date: the trend)
CREATE TABLE core.quality_runs (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id    bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    run_at      timestamptz NOT NULL DEFAULT now(),
    run_by      text NOT NULL DEFAULT core.current_actor(),
    trigger     text NOT NULL DEFAULT 'on-demand' CHECK (trigger IN ('on-demand', 'scheduled', 'change')),
    score       numeric(5, 2) NOT NULL,         -- 0..100 to two decimals: the model's quality score
    completeness numeric(5, 2) NOT NULL,
    entities    integer NOT NULL,
    summary     jsonb NOT NULL,                 -- counts: incomplete, failing (errors, warnings), orphans, stale, seals...
    by_type     jsonb NOT NULL,
    by_owner    jsonb NOT NULL,
    findings    jsonb NOT NULL,                 -- one row per problem: entity, kind, rule, message, responsible person
    seconds     numeric(8, 2) NOT NULL DEFAULT 0
);
CREATE INDEX quality_runs_model_idx ON core.quality_runs (model_id, run_at DESC);
COMMENT ON TABLE core.quality_runs IS 'Each quality measurement of a model, with its scores and findings (VAL-003, D239)';

-- ---------------------------------------------------------------- seals and "still current"
CREATE TABLE core.quality_seals (
    entity_id   bigint PRIMARY KEY REFERENCES core.entities (id) ON DELETE CASCADE,
    model_id    bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('seal', 'current')),   -- attested correct, or marked still current
    sealed_by   text NOT NULL,
    sealed_at   timestamptz NOT NULL DEFAULT now(),
    note        text NOT NULL DEFAULT ''
);
CREATE INDEX quality_seals_model_idx ON core.quality_seals (model_id);
COMMENT ON TABLE core.quality_seals IS 'An entity attested correct (VAL-007) or marked still current by a Model Admin (D239)';

-- ---------------------------------------------------------------- measuring in the background (D245)
-- Each entity's stored data quality (D245, D248): written by the background jobs (a whole model's measurement, or the
-- entities a commit touched, a few seconds later), never by triggers; grids, entity type scores and the Quality tab
-- read these, with when they were calculated. A single entity's page also checks it at once.
CREATE TABLE core.quality_entities (
    entity_id     bigint PRIMARY KEY REFERENCES core.entities (id) ON DELETE CASCADE,
    model_id      bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    entity_type   text NOT NULL,                -- the type code
    row           jsonb NOT NULL,               -- score, completeness, failing, stale, seal, responsible, owner...
    fields        jsonb NOT NULL DEFAULT '{}',  -- per field: why it lowers data quality
    calculated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX quality_entities_model_idx ON core.quality_entities (model_id, entity_type);
COMMENT ON TABLE core.quality_entities IS 'Each entity''s data quality as last calculated by a background job (D245, D248)';

-- Each measurement asked for (Measure now, Measure all, Recalculate): queued, run by the job runner, then done or failed.
CREATE TABLE core.quality_requests (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id     bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    requested_by text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    status       text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    started_at   timestamptz,
    finished_at  timestamptz,
    score        numeric(5, 2),
    error        text NOT NULL DEFAULT ''
);
CREATE INDEX quality_requests_model_idx ON core.quality_requests (model_id, requested_at DESC);
COMMENT ON TABLE core.quality_requests IS 'Quality measurements asked for and run in the background (D245)';

-- ---------------------------------------------------------------- "not applicable" on one entity (D246)
-- An item (an attribute, or the description) that does not apply to one entity: left out of its completeness once a
-- Model Admin of the model approves (a Model Admin's own applies at once).
CREATE TABLE core.quality_exemptions (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid          uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id      bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    entity_id     bigint NOT NULL REFERENCES core.entities (id) ON DELETE CASCADE,
    item          text NOT NULL CHECK (item ~ '^(attr:.+|field:description)$'),
    reason        text NOT NULL CHECK (btrim(reason) <> ''),
    status        text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'withdrawn')),
    requested_by  text NOT NULL,
    requested_at  timestamptz NOT NULL DEFAULT now(),
    decided_by    text,
    decided_at    timestamptz,
    decision_note text NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX quality_exemptions_live_idx ON core.quality_exemptions (entity_id, item) WHERE status IN ('pending', 'approved');
CREATE INDEX quality_exemptions_model_idx ON core.quality_exemptions (model_id, status);
COMMENT ON TABLE core.quality_exemptions IS 'Items marked not applicable on one entity, approved by a Model Admin (D246)';

-- ---------------------------------------------------------------- model icons (D247)
-- Each model's icon: one from the built-in library (a name, eax/model_icons.py and services/web/src/modelIcons.js) or an
-- image uploaded for that model only (PNG, JPEG, WebP or SVG, up to 256 KB). Kept apart from core.models so read-only
-- and locked models can have one too; Model Admins (and Super Admins) set it.
CREATE TABLE core.model_icons (
    model_id     bigint PRIMARY KEY REFERENCES core.models (id) ON DELETE CASCADE,
    library      text CHECK (library IS NULL OR library ~ '^[a-z][a-z0-9-]{1,30}$'),
    content_type text CHECK (content_type IS NULL OR content_type IN ('image/png', 'image/jpeg', 'image/webp', 'image/svg+xml')),
    data         bytea CHECK (data IS NULL OR octet_length(data) <= 262144),
    set_by       text NOT NULL DEFAULT core.current_actor(),
    set_at       timestamptz NOT NULL DEFAULT now(),
    CHECK ((library IS NOT NULL) <> (data IS NOT NULL)),
    CHECK ((data IS NULL) = (content_type IS NULL))
);
COMMENT ON TABLE core.model_icons IS 'Each model''s icon: from the built-in library or uploaded for that model (D247)';

-- ---------------------------------------------------------------- which models are measured (D242)
-- Super Admins and IT Admins choose; the choice stays. Archived models are never measured. Without a choice: project models
-- that are not frozen are measured; library (reference) models, root metamodels and frozen (locked) models are not.
CREATE TABLE core.quality_scope (
    model_id  bigint PRIMARY KEY REFERENCES core.models (id) ON DELETE CASCADE,
    measured  boolean NOT NULL,
    set_by    text NOT NULL,
    set_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.quality_scope IS 'Which models data quality measures, as Super and IT Admins chose (D242)';

-- ---------------------------------------------------------------- reminders already given
CREATE TABLE core.quality_told (
    entity_id   bigint NOT NULL REFERENCES core.entities (id) ON DELETE CASCADE,
    problem     text NOT NULL,                  -- incomplete, rule:<code>, stale, seal-broken, orphan
    model_id    bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    told        text NOT NULL,
    told_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (entity_id, problem)
);
COMMENT ON TABLE core.quality_told IS 'Which problems were already told to whom, so reminders as it happens are not repeated (D239)';

-- ---------------------------------------------------------------- the defaults for every model (the root of the hierarchy)
-- Quality is measured every night at 03:00 in the installation's time zone; an entity is stale after a year.
CREATE TABLE core.quality_defaults (
    one        boolean PRIMARY KEY DEFAULT true CHECK (one),
    stale_days integer NOT NULL DEFAULT 365 CHECK (stale_days BETWEEN 7 AND 3650),
    cron       text NOT NULL DEFAULT '0 3 * * 0',   -- every model measured again weekly (Sunday 03:00) by default
    -- the installation's score weights and colours (D244), set by Super Admins on Administration > Quality
    score_parts jsonb NOT NULL DEFAULT '{"completeness": 50, "rules": 30, "freshness": 20}' CHECK (jsonb_typeof(score_parts) = 'object'),
    bands       jsonb NOT NULL DEFAULT '{"green": 80, "amber": 60}' CHECK (jsonb_typeof(bands) = 'object'),
    modified_by text NOT NULL DEFAULT 'system',
    modified_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.quality_defaults IS 'The installation''s data quality defaults (D239, D244): stale period, schedule, score weights and colours; every model inherits what it and its ancestors do not set';
INSERT INTO core.quality_defaults DEFAULT VALUES;

-- the installer's login (the seed) may write them too
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.quality_settings, core.quality_rules, core.quality_changes,
              core.quality_runs, core.quality_seals, core.quality_told, core.quality_defaults, core.quality_scope,
              core.quality_entities, core.quality_requests, core.quality_exemptions, core.model_icons TO eax_migrator;
    END IF;
END;
$$;

-- ---------------------------------------------------------------- report views (Superset, QR-01 to QR-04, RPT-007)
-- Read through definer functions like the other report views; the Model filter (rpt.model_access) limits each person
-- to their models (D138). Each row links back to EA Explorer (link): the model's Quality tab or the entity.
CREATE FUNCTION rpt.f_quality_runs() RETURNS TABLE (
    model_id bigint, model_name text, run_at timestamptz, run_by text, trigger text, score numeric, completeness numeric,
    passing numeric, fresh numeric, entities integer, incomplete integer, failing integer, errors integer, stale integer,
    orphans integer, seals_valid integer, seals_broken integer, is_latest boolean, link text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
#variable_conflict use_column
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT r.model_id, m.name, r.run_at, r.run_by, r.trigger, r.score, r.completeness,
           (r.summary ->> 'passing')::numeric, (r.summary ->> 'fresh')::numeric, r.entities,
           (r.summary ->> 'incomplete')::int, (r.summary ->> 'failing')::int, (r.summary ->> 'errors')::int,
           (r.summary ->> 'stale')::int, (r.summary ->> 'orphans')::int,
           (r.summary -> 'seals' ->> 'valid')::int, (r.summary -> 'seals' ->> 'broken')::int,
           r.run_at = max(r.run_at) OVER (PARTITION BY r.model_id),
           '#/metamodel/' || m.guid || '/quality'
      FROM core.quality_runs r JOIN core.models m ON m.id = r.model_id AND NOT m.is_deleted;
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

-- the latest measurement of each model, one row per finding (the drill-down to the entities)
CREATE FUNCTION rpt.f_quality_findings() RETURNS TABLE (
    model_id bigint, model_name text, run_at timestamptz, display_id text, name text, entity_type text, owner text,
    responsible text, kind text, rule text, rule_name text, severity text, message text, link text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
#variable_conflict use_column
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT r.model_id, m.name, r.run_at, f ->> 'display_id', f ->> 'name', f ->> 'type_name',
           coalesce(nullif(f ->> 'owner', ''), '(no owner)'),
           (SELECT string_agg(x, ', ') FROM jsonb_array_elements_text(f -> 'responsible') x),
           f ->> 'kind', f ->> 'rule', f ->> 'rule_name', coalesce(f ->> 'severity', ''), f ->> 'message',
           '#/metamodel/' || m.guid || '/entity/' || (f ->> 'entity')
      FROM (SELECT DISTINCT ON (model_id) * FROM core.quality_runs ORDER BY model_id, run_at DESC) r
      JOIN core.models m ON m.id = r.model_id AND NOT m.is_deleted,
           jsonb_array_elements(r.findings) f;
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

-- the latest measurement of each model by entity type and by owner
CREATE FUNCTION rpt.f_quality_groups() RETURNS TABLE (
    model_id bigint, model_name text, run_at timestamptz, grouped_by text, name text, entities integer, completeness numeric,
    incomplete integer, failing integer, errors integer, stale integer, orphans integer, link text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
#variable_conflict use_column
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT r.model_id, m.name, r.run_at, g.grouped_by, x ->> 'name', (x ->> 'entities')::int, (x ->> 'completeness')::numeric,
           (x ->> 'incomplete')::int, (x ->> 'failing')::int, (x ->> 'errors')::int, (x ->> 'stale')::int,
           (x ->> 'orphans')::int, '#/metamodel/' || m.guid || '/quality'
      FROM (SELECT DISTINCT ON (model_id) * FROM core.quality_runs ORDER BY model_id, run_at DESC) r
      JOIN core.models m ON m.id = r.model_id AND NOT m.is_deleted,
           LATERAL (VALUES ('Entity type', r.by_type), ('Owner', r.by_owner)) g (grouped_by, rows),
           jsonb_array_elements(g.rows) x;
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

CREATE VIEW rpt.quality_runs AS SELECT * FROM rpt.f_quality_runs();
CREATE VIEW rpt.quality_findings AS SELECT * FROM rpt.f_quality_findings();
CREATE VIEW rpt.quality_groups AS SELECT * FROM rpt.f_quality_groups();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        GRANT SELECT ON rpt.quality_runs, rpt.quality_findings, rpt.quality_groups TO eax_report;
    END IF;
END;
$$;
