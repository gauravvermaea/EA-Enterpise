-- Phase 8.2 database checks: viewpoints as data, report audiences, the TOGAF, viewpoint and dependency report views.
-- Run as the API's login, with the laptop sample loaded (the demo estate Protea Insurance):
--   Get-Content services/api/tests/sql/phase8_2_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
-- Runs in one transaction that is rolled back. Ends with "phase 8.2 checks passed".
BEGIN;

DO $$
DECLARE
    v_model bigint;
    v_n     integer;
    v_bad   text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM core.schema_versions WHERE version = '0.8.2') THEN
        RAISE EXCEPTION 'schema version 0.8.2 (0012_viewpoints) is missing';
    END IF;

    -- the 26 built-in viewpoints (VP-26 Gap, D185), each with element types the ArchiMate 4 template has (Gap is added to a
    -- model with its first Gap entities, phase 8.3)
    ASSERT (SELECT count(*) FROM core.viewpoints WHERE is_builtin) = 26, '26 built-in viewpoints';
    ASSERT (SELECT array_agg(code ORDER BY code) FROM core.viewpoints WHERE is_builtin)
         = (SELECT array_agg(format('VP-%s', lpad(i::text, 2, '0')) ORDER BY i) FROM generate_series(1, 26) i), 'VP-01 to VP-26';
    PERFORM set_config('eax.rls_bypass', 'on', true);
    SELECT string_agg(DISTINCT t, ', ') INTO v_bad
      FROM core.viewpoints v, unnest(v.element_types) t
     WHERE v.is_builtin AND t <> 'Gap' AND NOT EXISTS (
           SELECT 1 FROM core.entity_types et JOIN core.models m ON m.id = et.model_id
            WHERE m.name = 'ArchiMate 4' AND et.code = t);
    ASSERT v_bad IS NULL, 'element types the template does not have: ' || coalesce(v_bad, '');

    -- built-in viewpoints are fixed; an organisation's own can be added (not with a VP-number)
    BEGIN
        UPDATE core.viewpoints SET name = 'Changed' WHERE code = 'VP-01';
        RAISE EXCEPTION 'a built-in viewpoint could be changed';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM NOT LIKE 'Not allowed%' THEN RAISE; END IF;
    END;
    BEGIN
        DELETE FROM core.viewpoints WHERE code = 'VP-02';
        RAISE EXCEPTION 'a built-in viewpoint could be deleted';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM NOT LIKE 'Not allowed%' THEN RAISE; END IF;
    END;
    BEGIN
        INSERT INTO core.viewpoints (code, name, element_types) VALUES ('VP-99', 'Mine', ARRAY['Capability']);
        RAISE EXCEPTION 'a VP-number could be taken';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM NOT LIKE 'Not allowed%' THEN RAISE; END IF;
    END;
    INSERT INTO core.viewpoints (code, name, element_types, created_by) VALUES ('OVP-01', 'Our capability and application view',
        ARRAY['Capability', 'ApplicationComponent'], 'check');
    UPDATE core.viewpoints SET concerns = 'Which applications serve which capabilities' WHERE code = 'OVP-01';
    ASSERT (SELECT count(*) FROM rpt.vp_elements e JOIN rpt.models m ON m.model_id = e.model_id
             WHERE e.viewpoint_code = 'OVP-01' AND m.model_name = 'Protea Insurance (demo estate)') = 65,
           'own viewpoint shows 37 capabilities and 28 applications';

    -- audiences (D153): every report and dashboard is for someone
    ASSERT (SELECT count(*) FROM core.report_audiences) = 29, '29 audiences';
    ASSERT EXISTS (SELECT 1 FROM core.report_audience_links WHERE report_code = 'SR-20' AND audience_code = 'cfo'), 'SR-20 for the CFO';
    ASSERT EXISTS (SELECT 1 FROM core.report_audience_links WHERE report_code = 'VP-19' AND audience_code = 'ceo'), 'VP-19 for the CEO';
    ASSERT (SELECT count(DISTINCT report_code) FROM core.report_audience_links WHERE report_code LIKE 'AU-%') = 29, 'one dashboard each';

    -- the report views have data for the demo estate
    SELECT model_id INTO v_model FROM rpt.models WHERE model_name = 'Protea Insurance (demo estate)';
    ASSERT v_model IS NOT NULL, 'the demo estate is loaded (laptop sample)';
    ASSERT (SELECT count(DISTINCT viewpoint_code) FROM rpt.vp_elements WHERE model_id = v_model) >= 25, 'every viewpoint has elements';
    ASSERT (SELECT count(*) FROM rpt.vp_relationships WHERE model_id = v_model AND viewpoint_code = 'VP-11') > 50, 'application cooperation';
    ASSERT (SELECT count(*) FROM rpt.vp_element_values WHERE model_id = v_model AND viewpoint_code = 'VP-19' AND is_heat_attribute) = 37,
           'capability map heat attribute (maturity) on every capability';
    ASSERT (SELECT count(*) FROM rpt.tc_principles WHERE model_id = v_model) = 6, 'principles catalogue';
    ASSERT (SELECT count(*) FROM rpt.tc_requirements WHERE model_id = v_model AND realisations > 0) = 8, 'every requirement realised';
    ASSERT (SELECT count(*) FROM rpt.tc_roadmap WHERE model_id = v_model) = 14, 'roadmap: 6 work packages, 5 deliverables, 3 plateaus';
    ASSERT (SELECT count(*) FROM rpt.tc_motivation_chain WHERE model_id = v_model AND goal IS NOT NULL) > 0, 'driver to goal';
    ASSERT (SELECT count(*) FROM rpt.tm_data_security WHERE model_id = v_model AND classification = 'Restricted') > 0, 'data security';
    ASSERT (SELECT count(*) FROM rpt.tm_capability_org WHERE model_id = v_model) > 0, 'capability and organisation';
    ASSERT (SELECT count(*) FROM rpt.dr_impact_chain WHERE model_id = v_model AND value_stream IS NOT NULL) > 0, 'technology to value stream';
    ASSERT (SELECT max(dependants) FROM rpt.dr_fan WHERE model_id = v_model) >= 10, 'hot spots';
    SELECT count(DISTINCT direction) INTO v_n
      FROM rpt.f_dependencies((SELECT entity_label FROM rpt.dr_entity_choices
                                WHERE model_id = v_model AND entity_label LIKE 'Claims Platform (%'), 6)
     WHERE model_id = v_model;
    ASSERT v_n = 2, 'dependencies both ways from Claims Platform';
    ASSERT (SELECT max(depth) FROM rpt.f_dependencies((SELECT entity_label FROM rpt.dr_entity_choices
                                WHERE model_id = v_model AND entity_label LIKE 'Claims Platform (%'), 2)) = 2, 'steps respected';
    PERFORM set_config('eax.rls_bypass', '', true);
END $$;

SELECT 'phase 8.2 checks passed' AS result;
ROLLBACK;
