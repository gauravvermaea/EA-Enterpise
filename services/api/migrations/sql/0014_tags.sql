-- =====================================================================================
-- 0014_tags: build phase 8.3 (version 0.8.4), model tags, comparison and gap analysis (D172)
--   * model tags: a frozen snapshot of a model (its metamodel and every entity, value and relationship) under a
--     name; anyone who changes the model's content tags it; a locked tag is never changed or deleted
--   * making a tag the latest: the current version is tagged first, then the tag overwrites the model
--     (metamodel and content, a complete override: parts added since are removed) as one commit (kind restore)
--   * comparison profiles: which entity types, fields and relationship types a comparison takes
--   * gap analyses: two sides compared (models or tags), when and by whom, the TOGAF template used, and one row
--     per gap (kept, changed, new, eliminated) with its note, resolution, work packages and Gap entity
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.8.4', '0014_tags', 'Phase 8.3: model tags (snapshots), comparison profiles, gap analyses and their report views');

-- a restore is a commit of its own kind (it can itself be rolled back, or overridden by restoring another tag)
ALTER TABLE core.commits DROP CONSTRAINT IF EXISTS commits_kind_check;
ALTER TABLE core.commits ADD CONSTRAINT commits_kind_check CHECK (kind IN ('commit', 'rollback', 'restore', 'merge'));

-- ---------------------------------------------------------------- model tags (frozen snapshots, D172)
CREATE TABLE core.model_tags (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid              uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id          bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    name              text NOT NULL CHECK (btrim(name) <> ''),
    description       text NOT NULL DEFAULT '',
    kind              text NOT NULL DEFAULT 'manual' CHECK (kind IN ('manual', 'before-restore', 'backup')),
    is_locked         boolean NOT NULL DEFAULT false,
    commit_number     integer NOT NULL DEFAULT 0,            -- the last commit when tagged
    metamodel_version integer NOT NULL DEFAULT 1,
    spec              jsonb NOT NULL,                        -- the metamodel (eax-metamodel/1)
    snapshot          jsonb NOT NULL,                        -- {entities: {guid: state}, relationships: {guid: state}}
    entity_count      integer NOT NULL DEFAULT 0,
    relationship_count integer NOT NULL DEFAULT 0,
    created_by        text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    locked_by         text,
    locked_at         timestamptz,
    restored_at       timestamptz,                          -- the last time it was made the latest
    restored_by       text
);
CREATE UNIQUE INDEX model_tags_name_idx ON core.model_tags (model_id, lower(name));
COMMENT ON TABLE core.model_tags IS 'A named, frozen snapshot of a model: metamodel and content (D172)';

-- a locked tag is never changed (apart from being restored) or deleted
CREATE FUNCTION core.model_tags_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.is_locked THEN
            RAISE EXCEPTION 'The tag "%" is locked: it cannot be deleted', OLD.name USING ERRCODE = 'insufficient_privilege';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.is_locked AND NEW.is_locked AND (NEW.name <> OLD.name OR NEW.description <> OLD.description
        OR NEW.spec <> OLD.spec OR NEW.snapshot <> OLD.snapshot) THEN
        RAISE EXCEPTION 'The tag "%" is locked: it cannot be changed', OLD.name USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER model_tags_guard BEFORE UPDATE OR DELETE ON core.model_tags FOR EACH ROW EXECUTE FUNCTION core.model_tags_guard();

-- ---------------------------------------------------------------- comparison profiles
CREATE TABLE core.compare_profiles (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    name        text NOT NULL CHECK (btrim(name) <> ''),     -- shared by everyone; its maker (or a Super Admin) deletes it
    settings    jsonb NOT NULL,          -- {types: {code: [fields]}, relationship_types: [...], metamodel: bool}
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX compare_profiles_name_idx ON core.compare_profiles (lower(name));
COMMENT ON TABLE core.compare_profiles IS 'Named choices of what a comparison takes: entity types, fields, relationship types';

-- ---------------------------------------------------------------- gap analyses (TOGAF)
CREATE TABLE core.gap_analyses (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id     bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,  -- the model the gaps are stored in (any project
                                                                                   -- model; may be the baseline's or target's): its roles decide access
    name         text NOT NULL CHECK (btrim(name) <> ''),
    description  text NOT NULL DEFAULT '',
    template     text NOT NULL DEFAULT 'all',                  -- a TOGAF gap template (eax/gaps.py)
    baseline     jsonb NOT NULL,     -- {kind: model|tag, model_id, model, tag_id, tag, commit, metamodel_version, label}
    target       jsonb NOT NULL,
    settings     jsonb NOT NULL DEFAULT '{}',
    summary      jsonb NOT NULL DEFAULT '{}',
    runs_made    integer NOT NULL DEFAULT 0,   -- results numbered so far: a deleted result's number is never used again
    compared_at  timestamptz NOT NULL DEFAULT now(),
    compared_by  text NOT NULL,
    created_by   text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX gap_analyses_name_idx ON core.gap_analyses (model_id, lower(name));
COMMENT ON TABLE core.gap_analyses IS 'A TOGAF gap analysis: a baseline and a target compared, kept with its decisions (D172)';

CREATE TABLE core.gap_items (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid           uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    analysis_id    bigint NOT NULL REFERENCES core.gap_analyses (id) ON DELETE CASCADE,
    match_key      text NOT NULL,                  -- baseline guid | target guid: kept when compared again
    entity_type    text NOT NULL,                  -- type code
    entity_type_name text NOT NULL DEFAULT '',
    layer          text NOT NULL DEFAULT '',
    name           text NOT NULL,
    status         text NOT NULL CHECK (status IN ('kept', 'changed', 'new', 'eliminated')),
    baseline_guid  uuid,
    baseline_name  text,
    target_guid    uuid,
    target_name    text,
    changes        jsonb NOT NULL DEFAULT '[]',    -- [{field, label, baseline, target}]
    note           text NOT NULL DEFAULT '',
    resolution     text NOT NULL DEFAULT '',
    work_packages  uuid[] NOT NULL DEFAULT '{}',
    gap_entity     uuid,                           -- the Gap entity made from it, if any
    gone           boolean NOT NULL DEFAULT false, -- no longer a gap when compared again (its notes are kept)
    modified_by    text,
    modified_at    timestamptz,
    UNIQUE (analysis_id, match_key)
);
CREATE INDEX gap_items_analysis_idx ON core.gap_items (analysis_id, status);
COMMENT ON TABLE core.gap_items IS 'One gap of a gap analysis: kept, changed, new or eliminated, with its decisions';

-- each time a gap analysis is compared (made or compared again) its result is kept as a numbered run, so two
-- results (of one analysis, or of two) can be compared later and Gap entities name the run they come from
CREATE TABLE core.gap_runs (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    analysis_id  bigint NOT NULL REFERENCES core.gap_analyses (id) ON DELETE CASCADE,
    number       integer NOT NULL,
    compared_at  timestamptz NOT NULL DEFAULT now(),
    compared_by  text NOT NULL,
    baseline     jsonb NOT NULL,
    target       jsonb NOT NULL,
    totals       jsonb NOT NULL DEFAULT '{}',
    items        jsonb NOT NULL DEFAULT '[]',   -- [{key, entity_type, entity_type_name, layer, name, status, resolution, note, changes}]
    UNIQUE (analysis_id, number)
);
COMMENT ON TABLE core.gap_runs IS 'Each result of a gap analysis (made or compared again), kept to compare results later';

-- ---------------------------------------------------------------- report views (Superset, GR-01 to GR-05)
-- The report login reads no core table: the gap views read through definer functions, like the other report views
-- (0009_reports); Superset's Model filter (rpt.model_access) limits each person to their models (D138)
CREATE FUNCTION rpt.f_gap_analyses() RETURNS TABLE (
    model_id bigint, model_name text, analysis_guid uuid, gap_analysis text, description text, template text, baseline text,
    target text, baseline_model text, baseline_tag text, target_model text, target_tag text, compared_at timestamptz,
    compared_by text, kept bigint, changed bigint, new bigint, eliminated bigint, undecided bigint, link text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
#variable_conflict use_column
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT a.model_id, m.name, a.guid, a.name, a.description, a.template,
           a.baseline ->> 'label', a.target ->> 'label', a.baseline ->> 'model', a.baseline ->> 'tag',
           a.target ->> 'model', a.target ->> 'tag', a.compared_at, a.compared_by,
           (SELECT count(*) FROM core.gap_items i WHERE i.analysis_id = a.id AND NOT i.gone AND i.status = 'kept'),
           (SELECT count(*) FROM core.gap_items i WHERE i.analysis_id = a.id AND NOT i.gone AND i.status = 'changed'),
           (SELECT count(*) FROM core.gap_items i WHERE i.analysis_id = a.id AND NOT i.gone AND i.status = 'new'),
           (SELECT count(*) FROM core.gap_items i WHERE i.analysis_id = a.id AND NOT i.gone AND i.status = 'eliminated'),
           (SELECT count(*) FROM core.gap_items i WHERE i.analysis_id = a.id AND NOT i.gone AND i.status <> 'kept' AND i.resolution = ''),
           '#/compare/gaps/' || a.guid
      FROM core.gap_analyses a JOIN core.models m ON m.id = a.model_id AND NOT m.is_deleted;
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

CREATE FUNCTION rpt.f_gap_items() RETURNS TABLE (
    model_id bigint, model_name text, gap_analysis text, template text, baseline text, target text, compared_at timestamptz,
    entity_type text, entity_type_name text, layer text, name text, status text, togaf_cell text, baseline_name text,
    target_name text, fields_changed integer, changed_fields text, note text, resolution text, work_packages text,
    work_package_count integer, has_gap_entity boolean, link text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
#variable_conflict use_column
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT a.model_id, m.name, a.name, a.template, a.baseline ->> 'label', a.target ->> 'label', a.compared_at,
           i.entity_type, i.entity_type_name, i.layer, i.name, i.status,
           CASE i.status WHEN 'kept' THEN 'Included' WHEN 'changed' THEN 'Changed' WHEN 'new' THEN 'New (gap: to build or buy)'
                         ELSE 'Eliminated (gap: to retire or replace)' END,
           i.baseline_name, i.target_name, jsonb_array_length(i.changes),
           (SELECT string_agg(c ->> 'label', ', ') FROM jsonb_array_elements(i.changes) c),
           i.note, nullif(i.resolution, ''),
           (SELECT string_agg(w.name, ', ' ORDER BY w.name) FROM core.entities w WHERE w.guid = ANY (i.work_packages) AND NOT w.is_deleted),
           cardinality(i.work_packages), i.gap_entity IS NOT NULL, '#/compare/gaps/' || a.guid
      FROM core.gap_items i JOIN core.gap_analyses a ON a.id = i.analysis_id
      JOIN core.models m ON m.id = a.model_id AND NOT m.is_deleted
     WHERE NOT i.gone;
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

CREATE VIEW rpt.gap_analyses AS SELECT * FROM rpt.f_gap_analyses();
CREATE VIEW rpt.gap_items AS SELECT * FROM rpt.f_gap_items();

-- the TOGAF gap matrix: baseline elements down, target elements across, by type
CREATE VIEW rpt.gap_matrix AS
SELECT model_id, model_name, gap_analysis, entity_type_name, layer,
       coalesce(baseline_name, '(new)') AS baseline_element, coalesce(target_name, '(eliminated)') AS target_element,
       togaf_cell, status, resolution, link
  FROM rpt.gap_items;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        GRANT SELECT ON rpt.gap_analyses, rpt.gap_items, rpt.gap_matrix TO eax_report;
    END IF;
END;
$$;
