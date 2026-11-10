-- =====================================================================================
-- 0035_kpi_odata_reports: version 0.17.0, batch 1 (D421): KPI trends, the OData feed and the report designer (phase 24,
-- D365, D430 to D435)
--   * a Model Admin's own KPIs: a count of entities of a type, or the sum of a number attribute, with one filter (D432)
--   * KPI snapshots: the standard set and the model's own KPIs, kept on the 1st of each month and on every tag (D431),
--     one row per KPI and dimension (e.g. Entities by type: one row per type)
--   * report designs: a type, its columns, related types and filters, kept with the SQL made from them; Superset makes its
--     dataset from it when the person opens it (D434)
--   * report views for Superset: rpt.kpi_trends (report KR-01) and rpt.report_designs (read by the Superset page that
--     makes a design's dataset)
-- The OData feed needs no tables: it reads the repository as the person (D433).
-- Rows only: the rules are in eax/kpis.py, eax/report_designer.py and eax/odata.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.17.0', '0035_kpi_odata_reports', 'Batch 1 (D421): KPI trends, OData feed, report designer')
ON CONFLICT (version) DO NOTHING;   -- several 0.17.0 migrations (batch 1): the first one writes the version

CREATE TABLE core.kpi_definitions (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid             uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    model_id         bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    name             text NOT NULL CHECK (btrim(name) <> ''),
    kind             text NOT NULL CHECK (kind IN ('count', 'sum')),
    entity_type_code text NOT NULL,                       -- the type counted or added up (by code: survives a metamodel copy)
    attribute_code   text NOT NULL DEFAULT '',            -- a sum: the number attribute added up
    filter_attribute text NOT NULL DEFAULT '',            -- one filter (or none)
    filter_op        text NOT NULL DEFAULT '' CHECK (filter_op IN ('', 'equals', 'not-equals', 'contains', 'empty', 'not-empty',
                                                                   'more-than', 'less-than')),
    filter_value     text NOT NULL DEFAULT '',
    unit             text NOT NULL DEFAULT '',
    description      text NOT NULL DEFAULT '',
    is_deleted       boolean NOT NULL DEFAULT false,      -- no longer kept; its values stay in the snapshots
    created_by       text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    modified_by      text NOT NULL,
    modified_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX kpi_definitions_model ON core.kpi_definitions (model_id) WHERE NOT is_deleted;

CREATE TABLE core.kpi_snapshots (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid      uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    model_id  bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    taken_at  timestamptz NOT NULL DEFAULT now(),
    period    date,                                      -- monthly: the 1st of the month it stands for
    reason    text NOT NULL CHECK (reason IN ('monthly', 'tag')),
    tag_id    bigint REFERENCES core.model_tags (id) ON DELETE SET NULL,
    tag_name  text NOT NULL DEFAULT '',
    taken_by  text NOT NULL DEFAULT 'system',
    CHECK (reason <> 'monthly' OR period IS NOT NULL)
);
CREATE UNIQUE INDEX kpi_snapshots_month ON core.kpi_snapshots (model_id, period) WHERE reason = 'monthly';
CREATE INDEX kpi_snapshots_model ON core.kpi_snapshots (model_id, taken_at);

CREATE TABLE core.kpi_values (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id bigint NOT NULL REFERENCES core.kpi_snapshots (id) ON DELETE CASCADE,
    model_id    bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    kpi         text NOT NULL,                           -- a standard code (entities, total_cost...) or own:<definition guid>
    name        text NOT NULL,                           -- its name when kept
    kind        text NOT NULL CHECK (kind IN ('standard', 'own')),
    dimension   text NOT NULL DEFAULT '',                -- e.g. the entity type, the TIME class; '' for one number
    value       numeric                                  -- empty: not known then (a quality score never measured)
);
CREATE INDEX kpi_values_snapshot ON core.kpi_values (snapshot_id);
CREATE INDEX kpi_values_model ON core.kpi_values (model_id, kpi);

CREATE TABLE core.report_designs (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    model_id    bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    name        text NOT NULL CHECK (btrim(name) <> ''),
    spec        jsonb NOT NULL,                          -- {entity_type, columns, related, filters}
    sql         text NOT NULL,                           -- made from the spec by eax/report_designer.py
    is_deleted  boolean NOT NULL DEFAULT false,
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_by text NOT NULL,
    modified_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX report_designs_model ON core.report_designs (model_id) WHERE NOT is_deleted;

-- ---------------------------------------------------------------- report views (read with the report login, D138)
CREATE VIEW rpt.kpi_trends AS
SELECT s.model_id, m.model_name, s.taken_at, coalesce(s.period, s.taken_at::date) AS period, s.reason,
       s.tag_name, v.kpi AS kpi_code, v.name AS kpi, v.kind AS kpi_kind, v.dimension, v.value,
       (s.id = (SELECT max(s2.id) FROM core.kpi_snapshots s2 WHERE s2.model_id = s.model_id)) AS is_latest
  FROM core.kpi_values v JOIN core.kpi_snapshots s ON s.id = v.snapshot_id
  JOIN rpt.models m ON m.model_id = s.model_id;

CREATE VIEW rpt.report_designs AS
SELECT d.guid AS design_guid, d.model_id, d.name, d.sql, d.created_by, d.modified_at
  FROM core.report_designs d WHERE NOT d.is_deleted;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.kpi_definitions, core.kpi_snapshots, core.kpi_values, core.report_designs
            TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        GRANT SELECT ON rpt.kpi_trends, rpt.report_designs TO eax_report;
    END IF;
END;
$$;
