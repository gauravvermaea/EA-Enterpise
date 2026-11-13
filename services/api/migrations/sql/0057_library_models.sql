-- =====================================================================================
-- 0057_library_models: the read-only shared models' content in the library_models schema (R2.42, D633; owner,
--   12 Nov 2026, 21:25: "move them now", a library database with its own connection string; 13 Nov 2026: read from the
--   library schema by every screen, the full split, schemas only, no new database).
--   Each model's row stays in core.models (the directory every list, picker and link uses), with content_schema saying
--   where its content is. The content tables are made here, LIKE their core ones (columns, defaults, checks, indexes,
--   identity; no foreign keys, triggers or row security: the library is written only by the application when a model
--   moves in, and read by everyone). Their identity counters start at 1,000,000,000 so an id never means two rows.
--   The rows move model by model at start-up, in the background (eax/library_models.py). No version change.
-- =====================================================================================

CREATE SCHEMA IF NOT EXISTS library_models;

ALTER TABLE core.models ADD COLUMN IF NOT EXISTS content_schema text NOT NULL DEFAULT 'core';
ALTER TABLE core.models DROP CONSTRAINT IF EXISTS models_content_schema_check;
ALTER TABLE core.models ADD CONSTRAINT models_content_schema_check CHECK (content_schema IN ('core', 'library_models'));
COMMENT ON COLUMN core.models.content_schema IS 'R2.42: where the model''s content is: core, or library_models for a library model';

DO $$
DECLARE
    t text;
    a record;
BEGIN
    FOREACH t IN ARRAY ARRAY['layers', 'pick_lists', 'pick_list_values', 'attribute_types', 'entity_types', 'relationship_types',
                             'item_attributes', 'allowed_relationships', 'item_attribute_mappings', 'validation_rules',
                             'metamodel_versions', 'metamodel_version_changes', 'display_id_counters', 'model_icons',
                             'entities', 'entity_aliases', 'entity_icons', 'attribute_values', 'relationships'] LOOP
        IF to_regclass('core.' || t) IS NOT NULL AND to_regclass('library_models.' || t) IS NULL THEN
            EXECUTE format('CREATE TABLE library_models.%I (LIKE core.%I INCLUDING ALL)', t, t);
        END IF;
    END LOOP;
    IF to_regclass('library_models.row_versions') IS NULL THEN
        CREATE TABLE library_models.row_versions (LIKE history.row_versions INCLUDING ALL);
    END IF;
    -- a serial column copied LIKE its core table still counts with the core table's sequence: a sequence of its own
    FOR a IN SELECT c.relname, at.attname FROM pg_attribute at JOIN pg_class c ON c.oid = at.attrelid
               JOIN pg_namespace n ON n.oid = c.relnamespace JOIN pg_attrdef d ON d.adrelid = at.attrelid AND d.adnum = at.attnum
              WHERE n.nspname = 'library_models' AND c.relkind = 'r' AND pg_get_expr(d.adbin, d.adrelid) LIKE 'nextval(%'
                AND pg_get_expr(d.adbin, d.adrelid) NOT LIKE 'nextval(''library_models.%' LOOP
        EXECUTE format('CREATE SEQUENCE IF NOT EXISTS library_models.%I START 1000000000', a.relname || '_' || a.attname || '_seq');
        EXECUTE format('ALTER TABLE library_models.%I ALTER COLUMN %I SET DEFAULT nextval(%L)', a.relname, a.attname,
                       'library_models.' || a.relname || '_' || a.attname || '_seq');
        EXECUTE format('ALTER SEQUENCE library_models.%I OWNED BY library_models.%I.%I', a.relname || '_' || a.attname || '_seq',
                       a.relname, a.attname);
    END LOOP;
    -- a counter of its own, well above the repository's, so an id never means two rows
    FOR a IN SELECT c.relname, at.attname FROM pg_attribute at JOIN pg_class c ON c.oid = at.attrelid
               JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'library_models' AND c.relkind = 'r' AND at.attidentity IN ('a', 'd') LOOP
        EXECUTE format('ALTER TABLE library_models.%I ALTER COLUMN %I RESTART WITH 1000000000', a.relname, a.attname);
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_app') THEN
        GRANT USAGE ON SCHEMA library_models TO eax_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA library_models TO eax_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA library_models TO eax_app;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT USAGE ON SCHEMA library_models TO eax_migrator;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA library_models TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA library_models TO eax_migrator;
    END IF;
END;
$$;
