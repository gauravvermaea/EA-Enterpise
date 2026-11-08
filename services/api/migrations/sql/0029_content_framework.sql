-- =====================================================================================
-- 0029_content_framework: build phase 13.0.7 (version 0.14.7), the content framework on each project (D299)
--   * where an entity type sits in the content framework (fixed areas, listed in eax/content_framework.py)
--   * where a document type sits (the library's and each project's), and a document's own choice when it differs
--   * '' is "not chosen": the application then uses its default map (eax/seed/content_framework_map.json)
-- Rows only: the rules are in eax/content_framework.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.14.7', '0029_content_framework', 'Phase 13.0.7: the content framework on each project');

ALTER TABLE core.entity_types ADD COLUMN content_area text NOT NULL DEFAULT '';
ALTER TABLE proj.lib_items ADD COLUMN content_area text NOT NULL DEFAULT '';
ALTER TABLE proj.items ADD COLUMN content_area text NOT NULL DEFAULT '';
ALTER TABLE proj.documents ADD COLUMN content_area text NOT NULL DEFAULT '';

-- the project's organisation (owner, 8 Nov 2026, D302): who works on it and their role on it, flat (a matrix, no
-- hierarchy); typed in, and linked to an EA Explorer user when they are one
CREATE TABLE proj.org_people (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid        uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id  bigint NOT NULL REFERENCES proj.projects (id) ON DELETE CASCADE,
    name        text NOT NULL,
    role        text NOT NULL DEFAULT '',
    username    text NOT NULL DEFAULT '',
    sort_order  integer NOT NULL DEFAULT 0,
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    modified_by text,
    modified_at timestamptz
);
CREATE INDEX org_people_project ON proj.org_people (project_id, sort_order);
-- a stakeholder listed in the organisation stays linked to its row of the stakeholder matrix
ALTER TABLE proj.org_people ADD COLUMN stakeholder_id bigint REFERENCES proj.stakeholders (id) ON DELETE SET NULL;
-- a stakeholder put into one of the project's models as a Stakeholder entity (D302): which entity, in which model
ALTER TABLE proj.stakeholders ADD COLUMN entity_guid uuid, ADD COLUMN entity_model uuid;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA proj TO eax_migrator;
    END IF;
END;
$$;
