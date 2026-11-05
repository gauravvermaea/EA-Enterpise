-- =====================================================================================
-- 0012_viewpoints: build phase 8.2 (version 0.8.2), reports and views (D161, pulled ahead of phase 8)
--   * viewpoints as data (D147): the 25 ArchiMate 4 example viewpoints VP-01 to VP-25 and an
--     organisation's own, each a set of element and relationship types (core.viewpoints)
--   * report audiences (D153): who a report interests (CEO, CFO, architects...); not roles, no access
--   * report views for the viewpoints (rpt.vp_*), the TOGAF catalogues and matrices the standard reports
--     did not have (rpt.tc_*, rpt.tm_*, rpt.type_pairs) and the dependency reports (rpt.dr_*, D149)
-- The seed (eax.seed.catalog) brings the built-in viewpoints and audiences in line with
-- eax/report_defs.py on every start; organisations' own viewpoints are kept.
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.8.2', '0012_viewpoints', 'Phase 8.2: viewpoints as data, report audiences, TOGAF catalogues and matrices, dependency reports');

-- ---------------------------------------------------------------- viewpoints
CREATE TABLE core.viewpoints (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid               uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    code               text NOT NULL UNIQUE CHECK (code ~ '^[A-Z]{2,4}-[0-9A-Za-z-]{1,20}$'),
    name               text NOT NULL CHECK (length(btrim(name)) > 0),
    category           text NOT NULL DEFAULT 'Organisation',
    purpose            text NOT NULL DEFAULT '',
    concerns           text NOT NULL DEFAULT '',
    stakeholders       text NOT NULL DEFAULT '',
    element_types      text[] NOT NULL CHECK (cardinality(element_types) > 0),
    relationship_types text[] NOT NULL DEFAULT '{}',
    heat_attribute     text NOT NULL DEFAULT 'Lifecycle',
    audiences          text[] NOT NULL DEFAULT '{}',
    is_builtin         boolean NOT NULL DEFAULT false,
    sort_order         integer NOT NULL DEFAULT 1000,
    created_by         text NOT NULL DEFAULT 'system',
    created_at         timestamptz NOT NULL DEFAULT now(),
    modified_by        text NOT NULL DEFAULT 'system',
    modified_at        timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.viewpoints IS 'Viewpoints as data (D147, D161): VP-01 to VP-25 from ArchiMate 4 Appendix C, and an organisation''s own';

-- built-in viewpoints are the product's: only the installer's login (the seed) changes them
CREATE FUNCTION core.viewpoints_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_user <> 'eax_migrator' AND current_user <> 'postgres' THEN
        IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.is_builtin THEN
            RAISE EXCEPTION 'Not allowed: % is a built-in viewpoint and cannot be changed or deleted; copy it to make your own', OLD.code;
        END IF;
        IF TG_OP IN ('INSERT', 'UPDATE') AND NEW.is_builtin THEN
            RAISE EXCEPTION 'Not allowed: only the product''s own viewpoints are built in';
        END IF;
        IF TG_OP IN ('INSERT', 'UPDATE') AND NEW.code ~ '^VP-[0-9]+$' THEN
            RAISE EXCEPTION 'Not allowed: codes VP-<number> belong to the built-in viewpoints; use another code (for example OVP-01)';
        END IF;
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER viewpoints_guard BEFORE INSERT OR UPDATE OR DELETE ON core.viewpoints
    FOR EACH ROW EXECUTE FUNCTION core.viewpoints_guard();

-- ---------------------------------------------------------------- report audiences (D153)
CREATE TABLE core.report_audiences (
    code           text PRIMARY KEY CHECK (code ~ '^[a-z][a-z0-9_]{1,40}$'),
    name           text NOT NULL,
    audience_group text NOT NULL,
    sort_order     integer NOT NULL DEFAULT 1000
);
COMMENT ON TABLE core.report_audiences IS 'Who a report interests (D153): CEO, CFO, architects...; not roles, they give no access';

CREATE TABLE core.report_audience_links (
    report_code   text NOT NULL,
    audience_code text NOT NULL REFERENCES core.report_audiences (code) ON DELETE CASCADE,
    PRIMARY KEY (report_code, audience_code)
);
COMMENT ON TABLE core.report_audience_links IS 'Which audiences each report and dashboard is for (D153)';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.viewpoints, core.report_audiences, core.report_audience_links TO eax_migrator;
    END IF;
END;
$$;

-- ---------------------------------------------------------------- viewpoint report views
CREATE VIEW rpt.viewpoints AS
SELECT code AS viewpoint_code, code || ' ' || name AS viewpoint, name, category, purpose, concerns, stakeholders,
       array_to_string(element_types, ', ') AS element_types, array_to_string(relationship_types, ', ') AS relationship_types,
       heat_attribute, is_builtin, sort_order
  FROM core.viewpoints;

-- every entity of every model, once for each viewpoint whose element types include its type
CREATE VIEW rpt.vp_elements AS
SELECT v.code AS viewpoint_code, v.code || ' ' || v.name AS viewpoint, v.category AS viewpoint_category,
       e.model_id, e.model_name, e.entity_id, e.display_id, e.name, e.description, e.entity_type_code, e.entity_type,
       e.layer, e.parent_name AS parent, e.status, e.owner, e.lifecycle, e.criticality, e.annual_cost, e.vendor,
       e.maturity, e.data_classification, e.priority, e.architecture_state, e.time_classification, e.link
  FROM rpt.entity_std e JOIN core.viewpoints v ON e.entity_type_code = ANY (v.element_types);

-- the relationships a viewpoint shows: both ends of a type it includes, and a relationship type it includes
CREATE VIEW rpt.vp_relationships AS
SELECT v.code AS viewpoint_code, v.code || ' ' || v.name AS viewpoint, r.model_id, r.model_name,
       r.source_name, r.source_type, r.relationship_type, r.verb, r.target_name, r.target_type, r.name, r.allowed,
       1 AS relationships
  FROM rpt.relationships r JOIN core.viewpoints v
    ON r.source_type_code = ANY (v.element_types) AND r.target_type_code = ANY (v.element_types)
   AND (cardinality(v.relationship_types) = 0 OR r.relationship_type_code = ANY (v.relationship_types));

-- the attribute values of a viewpoint's elements, for heat maps coloured by any attribute
CREATE VIEW rpt.vp_element_values AS
SELECT v.code AS viewpoint_code, v.code || ' ' || v.name AS viewpoint, e.model_id, e.model_name, e.entity_type, e.name,
       a.attribute_code, a.attribute, coalesce(nullif(a.value_display, ''), '(empty)') AS value,
       (a.attribute_code = v.heat_attribute) AS is_heat_attribute, e.link
  FROM rpt.entities e JOIN core.viewpoints v ON e.entity_type_code = ANY (v.element_types)
  JOIN rpt.entity_values a ON a.entity_id = e.entity_id;

-- ---------------------------------------------------------------- TOGAF catalogues and matrices (TC, TM)
-- any type against any type (the matrix reports choose their types)
CREATE VIEW rpt.type_pairs AS SELECT * FROM rpt.entity_pairs;

CREATE VIEW rpt.tc_principles AS
SELECT p.model_id, p.model_name, p.display_id, p.name, p.description, p.owner, p.priority, p.status,
       (SELECT string_agg(DISTINCT x.b_name, ', ') FROM rpt.entity_pairs x
         WHERE x.a_id = p.entity_id AND x.b_type_code IN ('Goal', 'Outcome')) AS supports_goals,
       (SELECT string_agg(DISTINCT x.b_name, ', ') FROM rpt.entity_pairs x
         WHERE x.a_id = p.entity_id AND x.b_type_code = 'Requirement') AS realised_by_requirements,
       p.link
  FROM rpt.entity_std p WHERE p.entity_type_code = 'Principle';

CREATE VIEW rpt.tc_stakeholders AS
SELECT s.model_id, s.model_name, s.name AS stakeholder, s.description, s.owner, x.b_type AS concern_type,
       x.b_name AS concern, x.relationship_type, s.link
  FROM rpt.entity_std s
  LEFT JOIN rpt.entity_pairs x ON x.a_id = s.entity_id
       AND x.b_type_code IN ('Driver', 'Goal', 'Outcome', 'Requirement', 'Assessment', 'Principle', 'Value', 'ValueStream')
 WHERE s.entity_type_code = 'Stakeholder';

-- driver, then the assessments, goals, outcomes and requirements linked to it (directly or one step on)
CREATE VIEW rpt.tc_motivation_chain AS
WITH p AS (SELECT a_id, a_name, b_id, b_name, b_type_code, model_id, model_name FROM rpt.entity_pairs)
SELECT d.model_id, d.model_name, d.name AS driver, asm.b_name AS assessment, g.name AS goal, o.b_name AS outcome,
       rq.b_name AS requirement, gs.measure AS goal_measure, gs.priority AS goal_priority
  FROM rpt.entities d
  LEFT JOIN p asm ON asm.a_id = d.entity_id AND asm.b_type_code = 'Assessment'
  LEFT JOIN LATERAL (
        SELECT DISTINCT q.b_id AS id, q.b_name AS name FROM p q
         WHERE q.b_type_code = 'Goal' AND (q.a_id = d.entity_id OR q.a_id = asm.b_id)) g ON true
  LEFT JOIN rpt.entity_std gs ON gs.entity_id = g.id
  LEFT JOIN p o ON o.a_id = g.id AND o.b_type_code = 'Outcome'
  LEFT JOIN p rq ON rq.a_id = coalesce(o.b_id, g.id) AND rq.b_type_code = 'Requirement'
 WHERE d.entity_type_code = 'Driver';

CREATE VIEW rpt.tc_requirements AS
SELECT q.model_id, q.model_name, q.display_id, q.name, q.description, q.owner, q.priority, q.status,
       (SELECT string_agg(DISTINCT r.target_name, ', ') FROM rpt.relationships r
         WHERE r.source_id = q.entity_id AND r.relationship_type_code = 'Realization') AS realises,
       (SELECT string_agg(DISTINCT r.source_name || ' (' || r.source_type || ')', ', ') FROM rpt.relationships r
         WHERE r.target_id = q.entity_id AND r.relationship_type_code = 'Realization') AS realised_by,
       (SELECT count(*) FROM rpt.relationships r
         WHERE r.target_id = q.entity_id AND r.relationship_type_code = 'Realization') AS realisations,
       q.link
  FROM rpt.entity_std q WHERE q.entity_type_code = 'Requirement';

CREATE VIEW rpt.tc_locations AS
SELECT l.model_id, l.model_name, l.name AS location, l.description, x.b_type AS item_type, x.b_name AS item,
       e.layer AS item_layer, x.relationship_type, l.link
  FROM rpt.entities l
  LEFT JOIN rpt.entity_pairs x ON x.a_id = l.entity_id
  LEFT JOIN rpt.entities e ON e.entity_id = x.b_id
 WHERE l.entity_type_code = 'Location';

CREATE VIEW rpt.tc_products AS
SELECT p.model_id, p.model_name, p.name AS product, p.description, p.owner, p.lifecycle, x.b_type AS part_type,
       x.b_name AS part, x.relationship_type, p.link
  FROM rpt.entity_std p
  LEFT JOIN rpt.entity_pairs x ON x.a_id = p.entity_id
 WHERE p.entity_type_code = 'Product';

CREATE VIEW rpt.tc_measures AS
SELECT g.model_id, g.model_name, g.entity_type, g.display_id, g.name, g.description, g.owner, g.priority,
       coalesce(nullif(g.measure, ''), 'Not set') AS measure,
       (SELECT count(*) FROM rpt.relationships r WHERE r.target_id = g.entity_id
           AND r.relationship_type_code IN ('Realization', 'Influence')) AS contributors,
       g.link
  FROM rpt.entity_std g WHERE g.entity_type_code IN ('Goal', 'Outcome');

CREATE VIEW rpt.tc_roadmap AS
SELECT w.model_id, w.model_name, w.entity_type, w.display_id, w.name, w.description, w.owner, w.priority,
       w.architecture_state, w.start_date, w.end_date, (w.end_date - w.start_date) AS duration_days,
       coalesce(to_char(w.start_date, 'YYYY'), 'Not set') AS start_year,
       CASE WHEN w.start_date IS NULL OR w.end_date IS NULL THEN 'Not scheduled'
            WHEN w.end_date < current_date THEN 'Finished'
            WHEN w.start_date > current_date THEN 'Planned'
            ELSE 'Running' END AS schedule_status,
       (SELECT string_agg(DISTINCT r.target_name, ', ') FROM rpt.relationships r
         WHERE r.source_id = w.entity_id AND r.relationship_type_code IN ('Realization', 'Aggregation')) AS delivers,
       w.link
  FROM rpt.entity_std w WHERE w.entity_type_code IN ('WorkPackage', 'Deliverable', 'Plateau');

CREATE VIEW rpt.tc_roles AS
SELECT r.model_id, r.model_name, r.name AS role, r.description, r.owner,
       (SELECT string_agg(DISTINCT x.b_name, ', ') FROM rpt.entity_pairs x
         WHERE x.a_id = r.entity_id AND x.b_type_code IN ('BusinessActor', 'Collaboration')) AS filled_by,
       (SELECT string_agg(DISTINCT x.b_name, ', ') FROM rpt.entity_pairs x
         WHERE x.a_id = r.entity_id AND x.b_type_code IN ('Process', 'Function')) AS performs,
       (SELECT string_agg(DISTINCT x.b_name, ', ') FROM rpt.entity_pairs x
         WHERE x.a_id = r.entity_id AND x.b_type_code IN ('ApplicationComponent', 'Service')) AS uses,
       r.link
  FROM rpt.entity_std r WHERE r.entity_type_code = 'Role';

-- data security: who and what touches each item of data, with its classification
CREATE VIEW rpt.tm_data_security AS
SELECT d.model_id, d.model_name, d.entity_type AS data_type, d.name AS data, coalesce(d.data_classification, 'Not set') AS classification,
       CASE d.data_classification WHEN 'Restricted' THEN 1 WHEN 'Confidential' THEN 2 WHEN 'Internal' THEN 3
            WHEN 'Public' THEN 4 ELSE 5 END AS classification_rank,
       x.b_type AS accessed_by_type, x.b_name AS accessed_by, coalesce(nullif(x.access_type, ''), x.relationship_type) AS access,
       d.link
  FROM rpt.entity_std d
  JOIN rpt.entity_pairs x ON x.a_id = d.entity_id
       AND x.b_type_code IN ('ApplicationComponent', 'ApplicationInterface', 'Process', 'Function', 'Service', 'Role',
                             'BusinessActor', 'Collaboration', 'Node', 'SystemSoftware')
 WHERE d.entity_type_code IN ('BusinessObject', 'DataObject', 'Artifact');

-- capability and organisation: directly, or through the applications, processes, functions and services that
-- realise the capability and the organisation units and roles that use, perform or are served by them
CREATE VIEW rpt.tm_capability_org AS
WITH cap AS (SELECT entity_id, model_id, model_name, name FROM rpt.entities WHERE entity_type_code = 'Capability'),
org AS (SELECT entity_id FROM rpt.entities WHERE entity_type_code IN ('BusinessActor', 'Collaboration', 'Role'))
SELECT DISTINCT c.model_id, c.model_name, c.name AS capability, x.b_name AS organisation, x.b_type AS organisation_type,
       'direct' AS through, '' AS via
  FROM cap c JOIN rpt.entity_pairs x ON x.a_id = c.entity_id JOIN org o ON o.entity_id = x.b_id
UNION
SELECT DISTINCT c.model_id, c.model_name, c.name, y.b_name, y.b_type, x.b_type, x.b_name
  FROM cap c
  JOIN rpt.entity_pairs x ON x.a_id = c.entity_id
       AND x.b_type_code IN ('ApplicationComponent', 'Process', 'Function', 'Service', 'Resource')
  JOIN rpt.entity_pairs y ON y.a_id = x.b_id JOIN org o ON o.entity_id = y.b_id;

-- ---------------------------------------------------------------- dependency reports (DR, D149)
-- A provider is the source of serving, realization, assignment, triggering, flow and influence relationships,
-- and the target of access, uses and runs-on relationships (the entity that accesses or uses it depends on it);
-- the parts of a whole (composition, aggregation) are providers of the whole.
CREATE VIEW rpt.dependency_edges AS
SELECT model_id, source_id AS provider, target_id AS dependant, relationship_type FROM rpt.relationships
 WHERE lower(relationship_type_code) IN ('serving', 'realization', 'assignment', 'triggering', 'flow', 'influence', 'supports')
UNION ALL
SELECT model_id, target_id, source_id, relationship_type FROM rpt.relationships
 WHERE lower(relationship_type_code) IN ('access', 'uses', 'runson', 'composition', 'aggregation');

-- the entities to choose from in DR-01, labelled so the same name in two types is told apart
CREATE VIEW rpt.dr_entity_choices AS
SELECT model_id, model_name, entity_type, name || ' (' || entity_type || ', ' || display_id || ')' AS entity_label
  FROM rpt.entities;

CREATE VIEW rpt.dr_steps AS SELECT v AS steps FROM generate_series(1, 6) AS v;

-- DR-01: from the chosen entity (by its label), what it depends on (upstream) and what depends on it
-- (downstream), up to p_steps steps, each entity once at its nearest distance, with one shortest path
CREATE FUNCTION rpt.f_dependencies(p_label text, p_steps integer DEFAULT 4) RETURNS TABLE (
    model_id bigint, model_name text, chosen_entity text, direction text, depth integer, entity text, entity_type text,
    layer text, lifecycle text, criticality numeric, last_relationship text, path text, link text)
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE root AS (
        SELECT c.model_id, e.entity_id, e.name FROM rpt.dr_entity_choices c
          JOIN rpt.entities e ON e.model_id = c.model_id
           AND c.entity_label = e.name || ' (' || e.entity_type || ', ' || e.display_id || ')'
         WHERE c.entity_label = p_label
    ), edges AS (SELECT * FROM rpt.dependency_edges WHERE model_id IN (SELECT r.model_id FROM root r)),
    walk AS (
        SELECT r.model_id, r.entity_id AS root_id, 'Downstream: depends on it' AS dir, ed.dependant AS id, 1 AS depth,
               ARRAY[r.entity_id, ed.dependant] AS path, ed.relationship_type AS via
          FROM root r JOIN edges ed ON ed.provider = r.entity_id
        UNION ALL
        SELECT r.model_id, r.entity_id, 'Upstream: it depends on', ed.provider, 1, ARRAY[r.entity_id, ed.provider], ed.relationship_type
          FROM root r JOIN edges ed ON ed.dependant = r.entity_id
        UNION ALL
        SELECT w.model_id, w.root_id, w.dir, CASE WHEN w.dir LIKE 'Down%' THEN ed.dependant ELSE ed.provider END, w.depth + 1,
               w.path || CASE WHEN w.dir LIKE 'Down%' THEN ed.dependant ELSE ed.provider END, ed.relationship_type
          FROM walk w JOIN edges ed ON (w.dir LIKE 'Down%' AND ed.provider = w.id) OR (w.dir LIKE 'Up%' AND ed.dependant = w.id)
         WHERE w.depth < least(greatest(coalesce(p_steps, 4), 1), 6)
           AND NOT (CASE WHEN w.dir LIKE 'Down%' THEN ed.dependant ELSE ed.provider END) = ANY (w.path)
    ), best AS (
        SELECT DISTINCT ON (w.root_id, w.dir, w.id) w.* FROM walk w ORDER BY w.root_id, w.dir, w.id, w.depth
    )
    SELECT b.model_id, m.model_name, r.name, b.dir, b.depth, x.name, x.entity_type, x.layer, s.lifecycle, s.criticality, b.via,
           (SELECT string_agg(n.name, CASE WHEN b.dir LIKE 'Down%' THEN ' → ' ELSE ' ← ' END ORDER BY o)
              FROM unnest(b.path) WITH ORDINALITY AS u(eid, o) JOIN rpt.entities n ON n.entity_id = u.eid),
           x.link
      FROM best b JOIN root r ON r.entity_id = b.root_id JOIN rpt.models m ON m.model_id = b.model_id
      JOIN rpt.entities x ON x.entity_id = b.id LEFT JOIN rpt.entity_std s ON s.entity_id = b.id
$$;

-- DR-03: technology, the applications it serves, the behaviour they support, the capabilities and value streams
CREATE VIEW rpt.dr_impact_chain AS
WITH role AS (SELECT lower(entity_type_code) AS code, role FROM rpt.std_roles),
tech AS (SELECT s.* FROM rpt.entity_std s WHERE s.role = 'technology'),
app_of AS (   -- technology serving or realising an application (directly)
    SELECT DISTINCT e.provider AS tech_id, e.dependant AS app_id FROM rpt.dependency_edges e
      JOIN rpt.entities a ON a.entity_id = e.dependant JOIN role r ON r.code = lower(a.entity_type_code) AND r.role = 'application'
), beh_of AS (
    SELECT DISTINCT p.a_id AS app_id, p.b_id AS beh_id, p.b_name AS behaviour FROM rpt.entity_pairs p
      JOIN role r ON r.code = lower(p.b_type_code) AND r.role IN ('process', 'function', 'service')
), cap_of AS (
    SELECT DISTINCT p.a_id AS from_id, p.b_id AS cap_id, p.b_name AS capability FROM rpt.entity_pairs p
     WHERE p.b_type_code = 'Capability'
), vs_of AS (
    SELECT DISTINCT p.a_id AS cap_id, p.b_name AS value_stream FROM rpt.entity_pairs p WHERE p.b_type_code = 'ValueStream'
)
SELECT DISTINCT t.model_id, t.model_name, t.name AS technology, t.entity_type AS technology_type, t.lifecycle AS technology_lifecycle,
       t.retirement_date AS end_of_life,
       CASE WHEN t.retirement_date < current_date OR t.lifecycle = 'Retired' THEN '1 Past end of life'
            WHEN t.retirement_date < current_date + interval '12 months' OR t.lifecycle IN ('Retiring', 'Phase Out') THEN '2 Within 12 months or phasing out'
            WHEN t.retirement_date < current_date + interval '36 months' THEN '3 Within 3 years'
            ELSE '4 No end of life soon' END AS risk,
       a.name AS application, a.criticality AS application_criticality, b.behaviour, c.capability, v.value_stream, a.link
  FROM tech t
  JOIN app_of ao ON ao.tech_id = t.entity_id
  JOIN rpt.entity_std a ON a.entity_id = ao.app_id
  LEFT JOIN beh_of b ON b.app_id = a.entity_id
  LEFT JOIN cap_of c ON c.from_id = a.entity_id
  LEFT JOIN vs_of v ON v.cap_id = c.cap_id;

-- DR-04: how many entities each entity depends on and how many depend on it (directly)
CREATE VIEW rpt.dr_fan AS
SELECT e.model_id, e.model_name, e.entity_type, e.layer, e.display_id, e.name, s.criticality, s.lifecycle,
       (SELECT count(DISTINCT d.dependant) FROM rpt.dependency_edges d WHERE d.provider = e.entity_id) AS dependants,
       (SELECT count(DISTINCT d.provider) FROM rpt.dependency_edges d WHERE d.dependant = e.entity_id) AS depends_on,
       e.link
  FROM rpt.entities e LEFT JOIN rpt.entity_std s ON s.entity_id = e.entity_id;

-- the read-only report login reads the new views and runs the dependency function
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_report') THEN
        GRANT SELECT ON rpt.viewpoints, rpt.vp_elements, rpt.vp_relationships, rpt.vp_element_values, rpt.type_pairs,
            rpt.tc_principles, rpt.tc_stakeholders, rpt.tc_motivation_chain, rpt.tc_requirements, rpt.tc_locations,
            rpt.tc_products, rpt.tc_measures, rpt.tc_roadmap, rpt.tc_roles, rpt.tm_data_security, rpt.tm_capability_org,
            rpt.dependency_edges, rpt.dr_entity_choices, rpt.dr_steps, rpt.dr_impact_chain, rpt.dr_fan TO eax_report;
        GRANT EXECUTE ON FUNCTION rpt.f_dependencies(text, integer) TO eax_report;
    END IF;
END;
$$;
