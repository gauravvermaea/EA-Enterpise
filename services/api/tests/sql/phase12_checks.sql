-- Phase 12 (0020_quality) checks, run as postgres (the report views are the report login's) after a measurement was kept.
-- Every line returns 'ok'.
SELECT CASE WHEN EXISTS (SELECT 1 FROM core.schema_versions WHERE version = '0.13.0') THEN 'ok' ELSE 'FAIL version' END;
SELECT CASE WHEN (SELECT stale_days FROM core.quality_defaults) = 365 AND (SELECT cron FROM core.quality_defaults) = '0 3 * * 0'
            THEN 'ok' ELSE 'FAIL defaults' END;
SELECT CASE WHEN count(*) > 0 THEN 'ok' ELSE 'FAIL no run' END FROM rpt.quality_runs WHERE is_latest;
SELECT CASE WHEN count(*) > 0 AND bool_and(link LIKE '#/metamodel/%/entity/%') THEN 'ok' ELSE 'FAIL findings' END FROM rpt.quality_findings;
SELECT CASE WHEN count(DISTINCT grouped_by) = 2 THEN 'ok' ELSE 'FAIL groups' END FROM rpt.quality_groups;
-- a rule code is unique per model, and a bad severity is refused
DO $$ BEGIN
    INSERT INTO core.quality_rules (model_id, code, name, kind, entity_type, severity)
    SELECT id, 'QR-99', 'x', 'naming', 'ApplicationComponent', 'fatal' FROM core.models WHERE kind_code = 'project' LIMIT 1;
    RAISE EXCEPTION 'FAIL severity accepted';
EXCEPTION WHEN check_violation THEN NULL; END $$;
SELECT 'ok';
