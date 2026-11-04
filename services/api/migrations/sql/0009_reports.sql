-- =====================================================================================
-- Phase 5 (version 0.5.0): report views, the first reports and the standard reports (D137-D140)
--   * rpt schema: views over the repository for Superset and other BI tools, read with the read-only
--     login eax_report. They read through SECURITY DEFINER functions (the views cannot reach the
--     core tables themselves), every row carries model_id, and Superset limits every dataset to the
--     models the signed-in person may read with one rule (rpt.model_access, D138).
--   * Generic views: rpt.models, rpt.entities, rpt.entity_values, rpt.relationships, rpt.entity_pairs,
--     rpt.changes, rpt.model_access, rpt.catalogue (the metamodel for report builders, D71), rpt.std_roles.
--   * Typed views: one per entity type code across every model, rpt.t_<type>, one column per
--     attribute, regenerated whenever a metamodel changes (rpt.refresh_typed_views, D139).
--   * Standard reports SR-01 to SR-15, the model overview and pick-list heatmaps (rpt.sr*, rpt.mo_*),
--     built on standard roles so they work on any model that keeps the standard types (D140).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.5.0', '0009_reports', 'Phase 5: report views, standard reports SR-01 to SR-15, model access for reports');

-- ---------------------------------------------------------------- who reads reports
-- The API records each person's global roles when they use it, so the reports know who is a Super
-- Admin (everything) without asking Keycloak.
CREATE TABLE core.known_users (
    username text PRIMARY KEY,
    roles    text[] NOT NULL DEFAULT '{}',
    seen_at  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.known_users IS 'Each person''s global roles as last seen by the API; read by rpt.model_access (D138)';

-- The row-security bypass counts for the API's login running its own SECURITY DEFINER report functions
-- (current_user is the owner there); any other login still gets nothing from setting it.
CREATE OR REPLACE FUNCTION core.may_read_model(p_model bigint) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT (current_setting('eax.rls_bypass', true) = 'on'
            AND current_user::regrole = (SELECT relowner::regrole FROM pg_class WHERE oid = 'core.models'::regclass))
        OR core.sees_every_model()
        OR p_model = ANY (core.readable_models())
$$;

-- ---------------------------------------------------------------- base functions (read everything)
CREATE FUNCTION rpt.f_models() RETURNS TABLE (
    model_id bigint, model_guid uuid, model_name text, model_kind text, version_label text, industry text, owner text,
    lifecycle text, is_draft boolean, is_locked boolean, library_state text, metamodel_name text, metamodel_version integer,
    source_model text, parent_model text, created_at timestamptz, modified_at timestamptz, source_model_id bigint)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT m.id, m.guid, m.name, m.kind_code, m.version_label, m.industry, m.owner, m.lifecycle, m.is_draft, m.is_locked,
           m.library_state, m.metamodel_name, m.metamodel_version, s.name, p.name, m.created_at, m.modified_at, m.source_model_id
      FROM core.models m LEFT JOIN core.models s ON s.id = m.source_model_id LEFT JOIN core.models p ON p.id = m.parent_model_id
     WHERE NOT m.is_deleted AND m.source_model_id IS NOT NULL;          -- not Root
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

CREATE FUNCTION rpt.f_entities() RETURNS TABLE (
    model_id bigint, model_name text, entity_id bigint, entity_guid uuid, display_id text, name text, description text,
    entity_type_code text, entity_type text, layer_code text, layer text, parent_id bigint, parent_name text, status text,
    origin_guid uuid, created_at timestamptz, created_by text, modified_at timestamptz, modified_by text, link text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT e.model_id, m.name, e.id, e.guid, e.display_id, e.name, e.description, t.code, t.name, l.code, l.name,
           e.parent_entity_id, pe.name, e.status_code, e.origin_guid, e.created_at, e.created_by, e.modified_at, e.modified_by,
           '#/metamodel/' || m.guid || '/entity/' || e.guid
      FROM core.entities e JOIN core.models m ON m.id = e.model_id AND NOT m.is_deleted
      JOIN core.entity_types t ON t.id = e.entity_type_id JOIN core.layers l ON l.id = t.layer_id
      LEFT JOIN core.entities pe ON pe.id = e.parent_entity_id
     WHERE NOT e.is_deleted;
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

CREATE FUNCTION rpt.f_entity_values() RETURNS TABLE (
    model_id bigint, entity_id bigint, entity_type_code text, attribute_code text, attribute text, data_type text,
    value_text text, value_number numeric, value_date date, value_bool boolean, value_display text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT v.model_id, v.entity_id, t.code, a.code, a.name, a.data_type_code, v.value_text, v.value_number, v.value_date, v.value_bool,
           coalesce(v.value_text, trim_scale(v.value_number)::text, v.value_date::text,
                    CASE WHEN v.value_bool THEN 'Yes' WHEN NOT v.value_bool THEN 'No' END, r.name)
      FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
      JOIN core.entities e ON e.id = v.entity_id AND NOT e.is_deleted
      JOIN core.entity_types t ON t.id = e.entity_type_id
      LEFT JOIN core.entities r ON r.id = v.value_ref
     WHERE NOT v.is_deleted AND v.entity_id IS NOT NULL;
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

CREATE FUNCTION rpt.f_relationships() RETURNS TABLE (
    model_id bigint, model_name text, relationship_guid uuid, relationship_type_code text, relationship_type text, verb text,
    source_id bigint, source_name text, source_type_code text, source_type text,
    target_id bigint, target_name text, target_type_code text, target_type text, name text, access_type text, allowed boolean)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT r.model_id, m.name, r.guid, rt.code, rt.name, rt.verb, s.id, s.name, st.code, st.name, t.id, t.name, tt.code, tt.name, r.name,
           (SELECT v.value_text FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
             WHERE v.relationship_id = r.id AND NOT v.is_deleted AND lower(a.code) IN ('accesstype', 'access', 'crud') LIMIT 1),
           EXISTS (SELECT 1 FROM core.allowed_relationships al WHERE al.relationship_type_id = r.relationship_type_id
                     AND al.source_type_id = s.entity_type_id AND al.target_type_id = t.entity_type_id AND NOT al.is_deleted)
      FROM core.relationships r JOIN core.models m ON m.id = r.model_id AND NOT m.is_deleted
      JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
      JOIN core.entities s ON s.id = r.source_entity_id AND NOT s.is_deleted JOIN core.entity_types st ON st.id = s.entity_type_id
      JOIN core.entities t ON t.id = r.target_entity_id AND NOT t.is_deleted JOIN core.entity_types tt ON tt.id = t.entity_type_id
     WHERE NOT r.is_deleted;
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

CREATE FUNCTION rpt.f_changes() RETURNS TABLE (
    model_id bigint, at timestamptz, changed_by text, kind text, operation text, entity_id bigint, label text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core, history AS $$
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT h.model_id, h.changed_at, h.changed_by,
           CASE h.table_name WHEN 'entities' THEN 'entity' WHEN 'attribute_values' THEN 'value' WHEN 'relationships' THEN 'relationship'
                ELSE 'metamodel' END,
           h.operation,
           CASE h.table_name WHEN 'entities' THEN h.row_id WHEN 'attribute_values' THEN (h.data->>'entity_id')::bigint
                WHEN 'relationships' THEN (h.data->>'source_entity_id')::bigint END,
           h.label
      FROM history.row_versions h
     WHERE h.model_id IS NOT NULL AND h.changed_at > now() - interval '2 years';
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

-- Who may read which model in the reports (D138): Super Admins every model; everyone the published
-- library (D98); people with a role on a model that model and the models it comes from.
CREATE FUNCTION rpt.f_model_access() RETURNS TABLE (username text, model_id bigint)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT lower(k.username), m.id FROM core.known_users k CROSS JOIN core.models m
     WHERE NOT m.is_deleted AND 'super-admin' = ANY (k.roles)
    UNION
    SELECT lower(k.username), m.id FROM core.known_users k CROSS JOIN core.models m
     WHERE NOT m.is_deleted AND m.kind_code IN ('template', 'reference') AND NOT m.is_draft
    UNION
    SELECT lower(u.username), u.model_id FROM core.model_users u
    UNION
    SELECT lower(u.username), a.ancestor_id FROM core.model_users u JOIN core.model_ancestors a ON a.model_id = u.model_id;
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

-- The metamodel for report builders (D71, RPT-021): every type and attribute, and the view and column it is in
CREATE FUNCTION rpt.snake(p text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT trim(both '_' FROM regexp_replace(lower(regexp_replace(regexp_replace(coalesce(p, ''), '([a-z0-9])([A-Z])', '\1_\2', 'g'),
                                                                  '([A-Z]+)([A-Z][a-z])', '\1_\2', 'g')), '[^a-z0-9]+', '_', 'g'))
$$;

CREATE FUNCTION rpt.f_catalogue() RETURNS TABLE (
    model_id bigint, model_name text, layer text, entity_type_code text, entity_type text, report_view text,
    attribute_code text, attribute text, data_type text, pick_list text, pick_list_values text, required boolean, report_column text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core AS $$
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    SELECT m.id, m.name, l.name, t.code, t.name, 'rpt.t_' || rpt.snake(t.code), a.code, a.name, a.data_type_code, pl.name,
           (SELECT string_agg(pv.value, ', ' ORDER BY pv.sort_order) FROM core.pick_list_values pv
             WHERE pv.pick_list_id = pl.id AND NOT pv.is_deleted),
           i.is_required, rpt.snake(a.code)
      FROM core.entity_types t JOIN core.models m ON m.id = t.model_id AND NOT m.is_deleted
      JOIN core.layers l ON l.id = t.layer_id
      LEFT JOIN core.item_attributes i ON i.entity_type_id = t.id AND NOT i.is_deleted
      LEFT JOIN core.attribute_types a ON a.id = i.attribute_type_id
      LEFT JOIN core.pick_lists pl ON pl.id = a.pick_list_id
     WHERE NOT t.is_deleted AND t.status_code <> 'retired';
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;

-- (the views call these as the person reading them, so the report login may run them: they give it what
-- the views give it, and nothing else in the repository)
REVOKE ALL ON FUNCTION rpt.f_models(), rpt.f_entities(), rpt.f_entity_values(), rpt.f_relationships(), rpt.f_changes(),
    rpt.f_model_access(), rpt.f_catalogue() FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        GRANT EXECUTE ON FUNCTION rpt.f_models(), rpt.f_entities(), rpt.f_entity_values(), rpt.f_relationships(), rpt.f_changes(),
            rpt.f_model_access(), rpt.f_catalogue() TO eax_report;
    END IF;
END;
$$;

-- ---------------------------------------------------------------- generic views
CREATE VIEW rpt.models AS SELECT * FROM rpt.f_models();
CREATE VIEW rpt.entities AS SELECT * FROM rpt.f_entities();
CREATE VIEW rpt.entity_values AS SELECT * FROM rpt.f_entity_values();
CREATE VIEW rpt.relationships AS SELECT * FROM rpt.f_relationships();
CREATE VIEW rpt.changes AS SELECT * FROM rpt.f_changes();
CREATE VIEW rpt.model_access AS SELECT * FROM rpt.f_model_access();
CREATE VIEW rpt.catalogue AS SELECT * FROM rpt.f_catalogue();

-- Both ends of every relationship, each way round: for matrices
CREATE VIEW rpt.entity_pairs AS
SELECT model_id, model_name, source_id AS a_id, source_name AS a_name, source_type_code AS a_type_code, source_type AS a_type,
       target_id AS b_id, target_name AS b_name, target_type_code AS b_type_code, target_type AS b_type,
       relationship_type_code, relationship_type, verb, access_type, 'outgoing' AS direction
  FROM rpt.relationships
UNION ALL
SELECT model_id, model_name, target_id, target_name, target_type_code, target_type,
       source_id, source_name, source_type_code, source_type,
       relationship_type_code, relationship_type, verb, access_type, 'incoming'
  FROM rpt.relationships;

-- Standard roles (RPT-018, D140): which entity type codes count as applications, capabilities, ... so the
-- standard reports work on ArchiMate 4, its copies, the reference models and an organisation's own roots
CREATE VIEW rpt.std_roles (role, entity_type_code) AS VALUES
    ('application', 'ApplicationComponent'), ('application', 'Application'),
    ('capability', 'Capability'),
    ('process', 'Process'), ('process', 'BusinessProcess'),
    ('function', 'Function'), ('function', 'BusinessFunction'),
    ('data', 'DataObject'), ('data', 'BusinessObject'), ('data', 'DataEntity'),
    ('technology', 'Node'), ('technology', 'SystemSoftware'), ('technology', 'Device'), ('technology', 'Platform'),
    ('technology', 'Equipment'), ('technology', 'Facility'), ('technology', 'CommunicationNetwork'),
    ('interface', 'ApplicationInterface'),
    ('actor', 'BusinessActor'), ('actor', 'Role'), ('actor', 'BusinessRole'), ('actor', 'Stakeholder'), ('actor', 'Collaboration'),
    ('motivation', 'Driver'), ('motivation', 'Goal'), ('motivation', 'Outcome'), ('motivation', 'Principle'),
    ('motivation', 'Requirement'), ('motivation', 'Constraint'), ('motivation', 'Assessment'), ('motivation', 'Meaning'),
    ('motivation', 'Value'),
    ('value_stream', 'ValueStream'), ('service', 'Service'), ('product', 'Product');

-- One row per entity with the attributes the standard reports use (by attribute code; empty when a
-- model does not have one), worked out once
CREATE VIEW rpt.entity_std AS
SELECT e.*, r.role,
       a.owner, a.lifecycle, a.criticality, a.annual_cost, a.vendor, a.version, a.hosting, a.go_live_date, a.retirement_date,
       a.data_classification, a.maturity, a.capability_level, a.process_level, a.domain, a.priority, a.measure,
       a.architecture_state, a.landscape_level, a.start_date, a.end_date, a.time_classification, a.functional_fit, a.technical_fit
  FROM rpt.entities e
  LEFT JOIN rpt.std_roles r ON lower(r.entity_type_code) = lower(e.entity_type_code)
  LEFT JOIN (
    SELECT entity_id,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'owner') AS owner,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'lifecycle') AS lifecycle,
           max(value_number) FILTER (WHERE lower(attribute_code) = 'criticality') AS criticality,
           max(value_number) FILTER (WHERE lower(attribute_code) IN ('annualcost', 'cost')) AS annual_cost,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'vendor') AS vendor,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'version') AS version,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'hosting') AS hosting,
           max(value_date) FILTER (WHERE lower(attribute_code) = 'golivedate') AS go_live_date,
           max(value_date) FILTER (WHERE lower(attribute_code) IN ('retirementdate', 'endoflife', 'endofsupport')) AS retirement_date,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'dataclassification') AS data_classification,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'maturity') AS maturity,
           max(value_number) FILTER (WHERE lower(attribute_code) = 'capabilitylevel') AS capability_level,
           max(value_number) FILTER (WHERE lower(attribute_code) = 'processlevel') AS process_level,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'domain') AS domain,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'priority') AS priority,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'measure') AS measure,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'architecturestate') AS architecture_state,
           max(value_display) FILTER (WHERE lower(attribute_code) = 'landscapelevel') AS landscape_level,
           max(value_date) FILTER (WHERE lower(attribute_code) = 'startdate') AS start_date,
           max(value_date) FILTER (WHERE lower(attribute_code) = 'enddate') AS end_date,
           max(value_display) FILTER (WHERE lower(attribute_code) IN ('timeclassification', 'time')) AS time_classification,
           max(value_number) FILTER (WHERE lower(attribute_code) = 'functionalfit') AS functional_fit,
           max(value_number) FILTER (WHERE lower(attribute_code) IN ('technicalfit', 'technicalhealth')) AS technical_fit
      FROM rpt.entity_values GROUP BY entity_id) a ON a.entity_id = e.entity_id;

-- ---------------------------------------------------------------- standard reports SR-01 to SR-30 (D137, D140)
CREATE VIEW rpt.sr01_application_inventory AS
SELECT model_id, model_name, entity_type, display_id, name, description, owner, lifecycle, criticality, annual_cost, vendor,
       version, hosting, go_live_date, retirement_date, architecture_state, time_classification, functional_fit, technical_fit,
       status, link
  FROM rpt.entity_std WHERE role = 'application';

CREATE VIEW rpt.sr02_capability_catalogue AS
SELECT c.model_id, c.model_name, c.display_id, c.name, c.description, c.parent_name AS parent, c.capability_level AS level,
       c.owner, c.maturity, c.criticality, c.lifecycle, coalesce(n.applications, 0) AS applications, c.link
  FROM rpt.entity_std c
  LEFT JOIN (SELECT p.a_id, count(DISTINCT p.b_id) AS applications
               FROM rpt.entity_pairs p JOIN rpt.std_roles r ON lower(r.entity_type_code) = lower(p.b_type_code)
              WHERE r.role = 'application' GROUP BY p.a_id) n ON n.a_id = c.entity_id
 WHERE c.role = 'capability';

CREATE VIEW rpt.sr03_technology_inventory AS
SELECT model_id, model_name, entity_type, display_id, name, description, owner, vendor, version, lifecycle, hosting,
       go_live_date, retirement_date AS end_of_life, annual_cost, criticality, link
  FROM rpt.entity_std WHERE role = 'technology';

CREATE VIEW rpt.sr04_data_catalogue AS
SELECT model_id, model_name, entity_type, display_id, name, description, owner, data_classification, lifecycle, link
  FROM rpt.entity_std WHERE role = 'data';

CREATE VIEW rpt.sr05_process_catalogue AS
SELECT p.model_id, p.model_name, p.entity_type, p.display_id, p.name, p.description, p.parent_name AS parent,
       p.process_level AS level, p.owner, p.domain, n.roles, p.link
  FROM rpt.entity_std p
  LEFT JOIN (SELECT x.a_id, string_agg(DISTINCT x.b_name, ', ') AS roles
               FROM rpt.entity_pairs x JOIN rpt.std_roles r ON lower(r.entity_type_code) = lower(x.b_type_code)
              WHERE r.role = 'actor' GROUP BY x.a_id) n ON n.a_id = p.entity_id
 WHERE p.role IN ('process', 'function');

CREATE VIEW rpt.sr06_interfaces AS
SELECT r.model_id, r.model_name, r.source_name AS source_application, r.relationship_type, r.target_name AS target_application,
       r.name AS flow, r.source_type, r.target_type
  FROM rpt.relationships r
  JOIN rpt.std_roles rs ON lower(rs.entity_type_code) = lower(r.source_type_code) AND rs.role IN ('application', 'interface')
  JOIN rpt.std_roles rt ON lower(rt.entity_type_code) = lower(r.target_type_code) AND rt.role IN ('application', 'interface')
 WHERE lower(r.relationship_type_code) IN ('flow', 'serving', 'triggering', 'uses', 'association');

CREATE VIEW rpt.sr07_actors AS
SELECT model_id, model_name, entity_type, display_id, name, description, owner, domain, parent_name AS part_of, link
  FROM rpt.entity_std WHERE role = 'actor';

CREATE VIEW rpt.sr08_motivation AS
SELECT model_id, model_name, entity_type, display_id, name, description, owner, priority, measure, link
  FROM rpt.entity_std WHERE role = 'motivation';

-- Matrices SR-09 to SR-15 (and SR-25): every pair of related entities with the standard roles of both ends
CREATE VIEW rpt.sr_matrix AS
SELECT p.model_id, p.model_name, ra.role AS a_role, p.a_type, p.a_name, rb.role AS b_role, p.b_type, p.b_name,
       p.relationship_type, p.verb, p.direction, coalesce(nullif(p.access_type, ''), p.relationship_type) AS cell
  FROM rpt.entity_pairs p
  JOIN rpt.std_roles ra ON lower(ra.entity_type_code) = lower(p.a_type_code)
  JOIN rpt.std_roles rb ON lower(rb.entity_type_code) = lower(p.b_type_code);

-- SR-16 capability heatmap: rpt.sr02_capability_catalogue (applications, maturity, criticality per capability)

-- SR-17 technology lifecycle and end of life
CREATE VIEW rpt.sr17_technology_lifecycle AS
SELECT t.*, coalesce(to_char(t.end_of_life, 'YYYY'), 'Not set') AS end_of_life_year,
       CASE WHEN t.end_of_life IS NULL THEN '5 Not set'
            WHEN t.end_of_life < current_date THEN '1 Past end of life'
            WHEN t.end_of_life < current_date + interval '12 months' THEN '2 Within 12 months'
            WHEN t.end_of_life < current_date + interval '36 months' THEN '3 Within 3 years'
            ELSE '4 Later' END AS end_of_life_status
  FROM rpt.sr03_technology_inventory t;

-- SR-18 TIME quadrant and SR-19 criticality against technical health (one view)
CREATE VIEW rpt.sr18_application_fit AS
SELECT model_id, model_name, display_id, name, owner, lifecycle, coalesce(time_classification, 'Not set') AS time_classification,
       functional_fit, technical_fit, criticality, annual_cost,
       CASE WHEN functional_fit IS NULL OR technical_fit IS NULL THEN 'Not assessed'
            WHEN functional_fit >= 3 AND technical_fit >= 3 THEN 'Invest'
            WHEN functional_fit >= 3 THEN 'Migrate'
            WHEN technical_fit >= 3 THEN 'Tolerate'
            ELSE 'Eliminate' END AS suggested_time,
       link
  FROM rpt.entity_std WHERE role = 'application';

-- SR-20 cost by capability: each application's annual cost, and the technology it uses, under every
-- capability it supports (an application supporting two capabilities counts under both)
CREATE VIEW rpt.sr20_cost_by_capability AS
SELECT c.model_id, c.model_name, c.name AS capability, c.capability_level, 'application' AS cost_of, a.name AS item, a.annual_cost
  FROM rpt.entity_pairs p
  JOIN rpt.entity_std c ON c.entity_id = p.a_id AND c.role = 'capability'
  JOIN rpt.entity_std a ON a.entity_id = p.b_id AND a.role = 'application'
UNION ALL
SELECT c.model_id, c.model_name, c.name, c.capability_level, 'technology', t.name, t.annual_cost
  FROM rpt.entity_pairs p
  JOIN rpt.entity_std c ON c.entity_id = p.a_id AND c.role = 'capability'
  JOIN rpt.entity_std a ON a.entity_id = p.b_id AND a.role = 'application'
  JOIN rpt.entity_pairs q ON q.a_id = a.entity_id
  JOIN rpt.entity_std t ON t.entity_id = q.b_id AND t.role = 'technology';

-- SR-21 vendor concentration
CREATE VIEW rpt.sr21_vendors AS
SELECT model_id, model_name, coalesce(nullif(vendor, ''), 'Not set') AS vendor, role, entity_type, name, lifecycle, annual_cost, link
  FROM rpt.entity_std WHERE role IN ('application', 'technology');

-- SR-22 impact analysis: everything that depends on each entity, up to four steps away. A provider is the
-- source of serving, realization, assignment, triggering, flow and influence relationships, and the target
-- of access, uses and runs-on relationships (the entity that accesses or uses it depends on it).
CREATE VIEW rpt.sr22_impact AS
WITH RECURSIVE edge AS (
    SELECT model_id, source_id AS provider, target_id AS dependant, relationship_type FROM rpt.relationships
     WHERE lower(relationship_type_code) IN ('serving', 'realization', 'assignment', 'triggering', 'flow', 'influence', 'supports')
    UNION ALL
    SELECT model_id, target_id, source_id, relationship_type FROM rpt.relationships
     WHERE lower(relationship_type_code) IN ('access', 'uses', 'runson')
), dep AS (
    SELECT e.model_id, e.provider AS root_id, e.dependant AS id, 1 AS depth, ARRAY[e.provider, e.dependant] AS path, e.relationship_type AS via
      FROM edge e
    UNION ALL
    SELECT d.model_id, d.root_id, e.dependant, d.depth + 1, d.path || e.dependant, e.relationship_type
      FROM dep d JOIN edge e ON e.provider = d.id
     WHERE d.depth < 4 AND NOT e.dependant = ANY (d.path)
)
SELECT d.model_id, r.model_name, r.name AS chosen_entity, r.entity_type AS chosen_type, d.depth, x.name AS dependant,
       x.entity_type AS dependant_type, d.via AS last_relationship,
       (SELECT string_agg(n.name, ' → ' ORDER BY o) FROM unnest(d.path) WITH ORDINALITY AS u(eid, o)
          JOIN rpt.entities n ON n.entity_id = u.eid) AS path,
       x.link
  FROM dep d JOIN rpt.entities r ON r.entity_id = d.root_id JOIN rpt.entities x ON x.entity_id = d.id;

-- SR-23 obsolescence risk: technology with an end of life (or phasing out), and the applications and
-- capabilities that use it; the dashboard bands it by the months a person chooses (default risk here)
CREATE VIEW rpt.sr23_obsolescence AS
WITH risky AS (
    SELECT entity_id, model_id, model_name, name, entity_type, end_of_life, lifecycle,
           CASE WHEN end_of_life < current_date OR lifecycle IN ('Retired') THEN '1 High'
                WHEN end_of_life < current_date + interval '12 months' OR lifecycle IN ('Retiring', 'Phase Out') THEN '2 Medium'
                ELSE '3 Low' END AS risk
      FROM (SELECT s.*, s.retirement_date AS end_of_life FROM rpt.entity_std s WHERE s.role = 'technology') t
     WHERE end_of_life IS NOT NULL OR lifecycle IN ('Retiring', 'Phase Out', 'Retired')
)
SELECT DISTINCT r.model_id, r.model_name, r.risk, r.name AS technology, r.entity_type AS technology_type, r.end_of_life, r.lifecycle,
       a.name AS application, c.name AS capability
  FROM risky r
  LEFT JOIN rpt.entity_pairs pa ON pa.a_id = r.entity_id
       AND pa.b_type_code IN (SELECT entity_type_code FROM rpt.std_roles WHERE role = 'application')
  LEFT JOIN rpt.entities a ON a.entity_id = pa.b_id
  LEFT JOIN rpt.entity_pairs pc ON pc.a_id = a.entity_id
       AND pc.b_type_code IN (SELECT entity_type_code FROM rpt.std_roles WHERE role = 'capability')
  LEFT JOIN rpt.entities c ON c.entity_id = pc.b_id;

-- SR-24 single points of failure: applications and technology ranked by how many entities depend on them,
-- and how many of those have no other provider of the same kind
CREATE VIEW rpt.sr24_single_points AS
WITH edge AS (
    SELECT DISTINCT provider, dependant FROM (
        SELECT source_id AS provider, target_id AS dependant FROM rpt.relationships
         WHERE lower(relationship_type_code) IN ('serving', 'realization', 'assignment', 'triggering', 'flow', 'supports')
        UNION ALL
        SELECT target_id, source_id FROM rpt.relationships WHERE lower(relationship_type_code) IN ('access', 'uses', 'runson')) x
), p AS (
    SELECT e.provider, e.dependant, s.role FROM edge e JOIN rpt.entity_std s ON s.entity_id = e.provider
     WHERE s.role IN ('application', 'technology')
), alt AS (
    SELECT dependant, role, count(*) AS providers FROM p GROUP BY dependant, role
)
SELECT s.model_id, s.model_name, s.role, s.entity_type, s.name, s.criticality, s.lifecycle,
       count(DISTINCT p.dependant) AS dependants,
       count(DISTINCT p.dependant) FILTER (WHERE alt.providers = 1) AS with_no_alternative, s.link
  FROM p JOIN alt ON alt.dependant = p.dependant AND alt.role = p.role
  JOIN rpt.entity_std s ON s.entity_id = p.provider
 GROUP BY s.model_id, s.model_name, s.role, s.entity_type, s.name, s.criticality, s.lifecycle, s.link;

-- SR-25 rationalisation candidates: capabilities served by more than one application
CREATE VIEW rpt.sr25_rationalisation AS
WITH m AS (
    SELECT model_id, model_name, a_name AS capability, b_name AS application
      FROM rpt.sr_matrix WHERE a_role = 'capability' AND b_role = 'application' GROUP BY 1, 2, 3, 4
)
SELECT m.model_id, m.model_name, m.capability, m.application, n.applications,
       (SELECT string_agg(DISTINCT o.application, ', ') FROM m o
         WHERE o.model_id = m.model_id AND o.capability = m.capability AND o.application <> m.application) AS overlaps_with
  FROM m JOIN (SELECT model_id, capability, count(*) AS applications FROM m GROUP BY 1, 2) n
    ON n.model_id = m.model_id AND n.capability = m.capability
 WHERE n.applications > 1;

-- SR-26 completeness: for each entity, how many of its type's attributes are filled, and required ones missing
CREATE VIEW rpt.sr26_completeness AS
WITH want AS (
    SELECT c.model_id, c.entity_type_code, c.attribute_code, c.attribute, c.required FROM rpt.catalogue c WHERE c.attribute_code IS NOT NULL
), got AS (
    SELECT entity_id, attribute_code FROM rpt.entity_values
     WHERE coalesce(value_text, value_number::text, value_date::text, value_bool::text, '') <> ''
)
SELECT e.model_id, e.model_name, e.entity_type, e.display_id, e.name, coalesce(nullif(s.owner, ''), 'Not set') AS owner,
       count(w.attribute_code) AS attributes, count(g.attribute_code) AS filled,
       count(w.attribute_code) FILTER (WHERE w.required) AS required,
       count(w.attribute_code) FILTER (WHERE w.required AND g.attribute_code IS NULL) AS required_missing,
       string_agg(w.attribute, ', ' ORDER BY w.attribute) FILTER (WHERE w.required AND g.attribute_code IS NULL) AS missing_required,
       round(100.0 * count(g.attribute_code) / nullif(count(w.attribute_code), 0), 1) AS completeness, e.link
  FROM rpt.entities e
  JOIN rpt.entity_std s ON s.entity_id = e.entity_id
  JOIN want w ON w.model_id = e.model_id AND w.entity_type_code = e.entity_type_code
  LEFT JOIN got g ON g.entity_id = e.entity_id AND g.attribute_code = w.attribute_code
 GROUP BY e.model_id, e.model_name, e.entity_type, e.display_id, e.name, s.owner, e.link;

-- SR-27 orphans: entities with no relationship, no parent and no children (the Failing checks screen lists
-- the required relationships that are missing)
CREATE VIEW rpt.sr27_orphans AS
SELECT e.model_id, e.model_name, e.layer, e.entity_type, e.display_id, e.name, e.parent_name AS parent, e.modified_at,
       e.modified_by, e.link
  FROM rpt.entities e
 WHERE NOT EXISTS (SELECT 1 FROM rpt.relationships r WHERE r.source_id = e.entity_id OR r.target_id = e.entity_id)
   AND e.parent_id IS NULL
   AND NOT EXISTS (SELECT 1 FROM rpt.entities c WHERE c.parent_id = e.entity_id);

-- SR-28 duplicate candidates: entities of the same type in the same model with similar names (trigram
-- similarity 0.6 or more; the same name after removing case, spaces and punctuation scores 1)
CREATE FUNCTION rpt.f_duplicates() RETURNS TABLE (
    model_id bigint, model_name text, entity_type text, name text, display_id text, similar_name text,
    similar_display_id text, similarity numeric, link text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, core, public AS $$
BEGIN
    PERFORM set_config('eax.rls_bypass', 'on', true);
    RETURN QUERY
    WITH e AS (
        SELECT x.id, x.model_id, x.entity_type_id, x.name, x.display_id, x.guid,
               regexp_replace(lower(x.name), '[^a-z0-9]+', '', 'g') AS norm
          FROM core.entities x JOIN core.models m ON m.id = x.model_id AND NOT m.is_deleted WHERE NOT x.is_deleted
    )
    SELECT a.model_id, m.name, t.name, a.name, a.display_id, b.name, b.display_id,
           round(CASE WHEN a.norm = b.norm THEN 1 ELSE similarity(a.name, b.name) END::numeric, 2),
           '#/metamodel/' || m.guid || '/entity/' || a.guid
      FROM e a JOIN e b ON b.model_id = a.model_id AND b.entity_type_id = a.entity_type_id AND b.id > a.id
       AND (a.norm = b.norm OR similarity(a.name, b.name) >= 0.6)
      JOIN core.models m ON m.id = a.model_id JOIN core.entity_types t ON t.id = a.entity_type_id;
    PERFORM set_config('eax.rls_bypass', '', true);
END;
$$;
REVOKE ALL ON FUNCTION rpt.f_duplicates() FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        GRANT EXECUTE ON FUNCTION rpt.f_duplicates() TO eax_report;
    END IF;
END;
$$;
CREATE VIEW rpt.sr28_duplicates AS SELECT * FROM rpt.f_duplicates();

-- SR-29 change activity: every change of the last two years, by model, person and kind
CREATE VIEW rpt.sr29_change_activity AS
SELECT c.model_id, m.model_name, c.at, date_trunc('week', c.at) AS week, c.changed_by, c.kind, c.operation,
       e.entity_type, c.label
  FROM rpt.changes c JOIN rpt.models m ON m.model_id = c.model_id
  LEFT JOIN rpt.entities e ON e.entity_id = c.entity_id;

-- SR-30 comparison with the source: each model created from another model, compared with it entity by
-- entity (matched by origin, D133): kept, changed (name, description or values), new, or removed.
-- Comparison with the model's own named versions and baselines comes with phase 24.1.
CREATE VIEW rpt.sr30_source_comparison AS
WITH v AS (
    SELECT entity_id, string_agg(attribute_code || '=' || coalesce(value_display, ''), '|' ORDER BY attribute_code) AS vals
      FROM rpt.entity_values GROUP BY entity_id
), c AS (
    SELECT m.model_id, m.model_name, src.model_id AS source_id, src.model_name AS source_name
      FROM rpt.models m JOIN rpt.models src ON src.model_id = m.source_model_id
)
SELECT c.model_id, c.model_name, c.source_name AS compared_with,
       CASE WHEN s.entity_id IS NULL THEN 'New'
            WHEN e.name IS DISTINCT FROM s.name OR e.description IS DISTINCT FROM s.description
                 OR coalesce(ve.vals, '') <> coalesce(vs.vals, '') THEN 'Changed'
            ELSE 'Kept' END AS status,
       e.entity_type, e.name, s.name AS name_in_source,
       concat_ws(', ', CASE WHEN e.name IS DISTINCT FROM s.name THEN 'name' END,
                       CASE WHEN e.description IS DISTINCT FROM s.description THEN 'description' END,
                       CASE WHEN s.entity_id IS NOT NULL AND coalesce(ve.vals, '') <> coalesce(vs.vals, '') THEN 'values' END) AS what_changed,
       e.link
  FROM c JOIN rpt.entities e ON e.model_id = c.model_id
  LEFT JOIN rpt.entities s ON s.model_id = c.source_id AND s.entity_guid = e.origin_guid
  LEFT JOIN v ve ON ve.entity_id = e.entity_id LEFT JOIN v vs ON vs.entity_id = s.entity_id
UNION ALL
SELECT c.model_id, c.model_name, c.source_name, 'Removed', s.entity_type, NULL, s.name, 'not in this model', s.link
  FROM c JOIN rpt.entities s ON s.model_id = c.source_id
 WHERE NOT EXISTS (SELECT 1 FROM rpt.entities e WHERE e.model_id = c.model_id AND e.origin_guid = s.entity_guid);

-- Heatmap thresholds (owner, 4 Nov 2026): the values a person can pick in a heatmap's threshold filters
-- (Medium from, High from, Red within, Amber within); the dashboards' datasets read the choice through
-- Superset's filter_values() and band each cell
CREATE VIEW rpt.heat_thresholds AS
SELECT v AS medium_from, v AS high_from, v AS red_within, v AS amber_within
  FROM unnest(ARRAY[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 18, 20, 24, 25, 30, 36, 40, 48, 50, 60, 72, 75, 100, 150, 200]) AS v;

-- ---------------------------------------------------------------- model overview (MOD-010) and heatmaps (RPT-006)
CREATE VIEW rpt.mo_type_counts AS
SELECT m.model_id, m.model_name, m.model_kind, l.layer, l.entity_type, count(e.entity_id) AS entities
  FROM rpt.models m
  JOIN (SELECT DISTINCT model_id, layer, entity_type FROM rpt.catalogue) l ON l.model_id = m.model_id
  LEFT JOIN rpt.entities e ON e.model_id = m.model_id AND e.entity_type = l.entity_type
 GROUP BY m.model_id, m.model_name, m.model_kind, l.layer, l.entity_type;

CREATE VIEW rpt.mo_recent_changes AS
SELECT c.model_id, m.model_name, c.at, c.changed_by, c.kind, c.operation, e.name AS entity, e.entity_type, c.label
  FROM rpt.changes c JOIN rpt.models m ON m.model_id = c.model_id
  LEFT JOIN rpt.entities e ON e.entity_id = c.entity_id
 WHERE c.at > now() - interval '90 days';

CREATE VIEW rpt.mo_pick_list_counts AS
SELECT v.model_id, e.model_name, e.entity_type, v.attribute, coalesce(v.value_display, '(empty)') AS value, count(*) AS entities
  FROM rpt.entity_values v JOIN rpt.entities e ON e.entity_id = v.entity_id
 WHERE v.data_type IN ('list', 'boolean', 'integer')
 GROUP BY v.model_id, e.model_name, e.entity_type, v.attribute, v.value_display;

-- ---------------------------------------------------------------- typed views (D139)
-- One view per entity type code across every model: rpt.t_<type> with the entity's own columns and one
-- column per attribute code the type has in any model. Regenerated when a metamodel changes; a view is
-- dropped and made again only when its definition changed.
CREATE TABLE rpt.typed_views (
    view_name   text PRIMARY KEY,
    type_code   text NOT NULL,
    definition  text NOT NULL,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON rpt.typed_views FROM eax_report;

CREATE FUNCTION rpt.refresh_typed_views() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, core, rpt AS $$
DECLARE
    t record;
    a record;
    v_cols text;
    v_name text;
    v_def text;
    v_col text;
    v_used text[];
    v_changed integer := 0;
    v_wanted text[] := ARRAY[]::text[];
    v_base text[] := ARRAY['model_id', 'model_name', 'entity_id', 'entity_guid', 'display_id', 'name', 'description', 'entity_type_code',
                           'entity_type', 'layer_code', 'layer', 'parent_id', 'parent_name', 'status', 'origin_guid', 'created_at',
                           'created_by', 'modified_at', 'modified_by', 'link'];
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('rpt.refresh_typed_views'));
    PERFORM set_config('eax.rls_bypass', 'on', true);
    FOR t IN SELECT DISTINCT et.code FROM core.entity_types et JOIN core.models m ON m.id = et.model_id AND NOT m.is_deleted
              WHERE NOT et.is_deleted ORDER BY et.code LOOP
        v_name := 't_' || rpt.snake(t.code);
        v_wanted := v_wanted || v_name;
        v_cols := '';
        v_used := v_base;
        FOR a IN
            SELECT lower(at.code) AS code, min(at.code) AS label,
                   mode() WITHIN GROUP (ORDER BY at.data_type_code) AS data_type
              FROM core.item_attributes i JOIN core.attribute_types at ON at.id = i.attribute_type_id
              JOIN core.entity_types et ON et.id = i.entity_type_id AND et.code = t.code AND NOT et.is_deleted
              JOIN core.models m ON m.id = i.model_id AND NOT m.is_deleted
             WHERE NOT i.is_deleted
             GROUP BY lower(at.code) ORDER BY 1
        LOOP
            v_col := rpt.snake(a.label);
            IF v_col = '' OR v_col = ANY (v_used) THEN v_col := 'a_' || v_col; END IF;
            v_used := v_used || v_col;
            v_cols := v_cols || format(', %s AS %I',
                CASE WHEN a.data_type IN ('integer', 'decimal', 'currency', 'percent')
                          THEN format('max(v.value_number) FILTER (WHERE lower(v.attribute_code) = %L)', a.code)
                     WHEN a.data_type = 'date' THEN format('max(v.value_date) FILTER (WHERE lower(v.attribute_code) = %L)', a.code)
                     WHEN a.data_type = 'boolean' THEN format('bool_or(v.value_bool) FILTER (WHERE lower(v.attribute_code) = %L)', a.code)
                     ELSE format('max(v.value_display) FILTER (WHERE lower(v.attribute_code) = %L)', a.code) END,
                v_col);
        END LOOP;
        v_def := format('SELECT e.*%s FROM rpt.entities e LEFT JOIN rpt.entity_values v ON v.entity_id = e.entity_id '
                        'WHERE e.entity_type_code = %L GROUP BY %s',
                        v_cols, t.code, (SELECT string_agg('e.' || quote_ident(c), ', ') FROM unnest(v_base) c));
        IF NOT EXISTS (SELECT 1 FROM rpt.typed_views WHERE view_name = v_name AND definition = v_def) THEN
            IF to_regclass('rpt.' || quote_ident(v_name)) IS NOT NULL THEN
                EXECUTE format('DROP VIEW rpt.%I', v_name);
            END IF;
            EXECUTE format('CREATE VIEW rpt.%I AS %s', v_name, v_def);
            EXECUTE format('COMMENT ON VIEW rpt.%I IS %L', v_name, 'Entities of type ' || t.code || ' in every model, one column per attribute (D139)');
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
                EXECUTE format('GRANT SELECT ON rpt.%I TO eax_report', v_name);
            END IF;
            INSERT INTO rpt.typed_views (view_name, type_code, definition) VALUES (v_name, t.code, v_def)
            ON CONFLICT (view_name) DO UPDATE SET definition = EXCLUDED.definition, type_code = EXCLUDED.type_code, refreshed_at = now();
            v_changed := v_changed + 1;
        END IF;
    END LOOP;
    -- types no model has any more
    FOR t IN SELECT view_name FROM rpt.typed_views WHERE NOT (view_name = ANY (v_wanted)) LOOP
        EXECUTE format('DROP VIEW IF EXISTS rpt.%I', t.view_name);
        DELETE FROM rpt.typed_views WHERE view_name = t.view_name;
        v_changed := v_changed + 1;
    END LOOP;
    PERFORM set_config('eax.rls_bypass', '', true);
    RETURN v_changed;
END;
$$;
REVOKE ALL ON FUNCTION rpt.refresh_typed_views() FROM PUBLIC;
-- the installer's login runs it after loading the built-in models (eax.seed)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT EXECUTE ON FUNCTION rpt.refresh_typed_views() TO eax_migrator;
        GRANT USAGE ON SCHEMA rpt TO eax_migrator;
    END IF;
END;
$$;

SELECT rpt.refresh_typed_views();

-- the read-only report login reads every rpt view (default privileges cover views made later by the API's login)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        GRANT USAGE ON SCHEMA rpt TO eax_report;
        GRANT SELECT ON ALL TABLES IN SCHEMA rpt TO eax_report;
        REVOKE ALL ON rpt.typed_views FROM eax_report;
        REVOKE ALL ON core.known_users FROM eax_report;
    END IF;
END;
$$;
