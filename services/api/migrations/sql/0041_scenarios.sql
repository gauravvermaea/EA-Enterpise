-- =====================================================================================
-- 0041_scenarios: version 0.18.0, scenario planning with AI (phase 27.1, D364, D490 to D495).
-- A project's scenario assessments: the comparison of its scenario models with the baseline as the author saw them, each
-- scenario's score and notes, the recommendation, and the Word document and governance decision made from it.
-- Rows only: who may read and record them, and every figure, are in eax/scenarios.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.18.0', '0041_scenarios', 'Scenario planning: a project''s scenario assessments')
ON CONFLICT (version) DO NOTHING;   -- several 0.18.0 migrations (batches 2 and 3): the first one writes the version

CREATE TABLE IF NOT EXISTS proj.scenario_assessments (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid              uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    project_id        bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    ref               text NOT NULL,                       -- SCN-001
    title             text NOT NULL,
    baseline_guid     uuid,
    baseline_name     text NOT NULL DEFAULT '',
    scenarios         jsonb NOT NULL DEFAULT '[]',          -- [{model, name, role, score, notes, figures, difference, suggested, comparison}]
    recommendation    text NOT NULL DEFAULT '',
    recommended_guid  uuid,
    recommended_name  text NOT NULL DEFAULT '',
    document_id       bigint REFERENCES proj.documents (id) ON DELETE SET NULL,
    gov_record_id     bigint REFERENCES proj.gov_records (id) ON DELETE SET NULL,
    via               text NOT NULL DEFAULT 'mcp',          -- mcp | screens
    created_by        text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, ref)
);
CREATE INDEX IF NOT EXISTS scenario_assessments_project ON proj.scenario_assessments (project_id, created_at DESC);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;
