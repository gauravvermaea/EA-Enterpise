-- =====================================================================================
-- EA Explorer phase 1: get_entity and get_entity_by_name
--
-- The repository stores content generically (one entity table, one attribute value table).
-- These functions turn it back into one ordinary table per entity type, built on demand from
-- the current metamodel, plus a table of each entity's relationships:
--
--   SELECT eax.get_entity('Application Component', 'apps');
--       -> {apps, apps_rel}
--   SELECT * FROM apps WHERE lifecycle = 'Production';
--   SELECT * FROM apps_rel WHERE relationship_type = 'Realization';
--
--   SELECT eax.get_entity_by_name('Application Component', 'Claims Platform', 'claims_app');
--
-- The caller always names the tables (p_table; the relationship table adds "_rel"), so two callers
-- or two calls never collide: our code uses a fresh guid-based name for every call (e_<32 hex>).
-- A name already in use in the session is refused, never replaced.
-- The tables are temporary: private to the caller's database session and dropped by PostgreSQL
-- when that connection closes (they never outlive the connection). Code that keeps connections in
-- a pool drops them itself with eax.drop_entity(name); the API pool also runs DISCARD TEMP when a
-- connection is returned.
-- Only models the caller may read are included (core.can_read_model). p_model is the model's
-- guid (the id the API and screens use).
-- =====================================================================================

CREATE SCHEMA IF NOT EXISTS eax;

-- Built-in columns of every entity table; an attribute whose column name clashes gets "_attr"
CREATE FUNCTION eax._reserved_columns() RETURNS text[] LANGUAGE sql IMMUTABLE AS $$
    SELECT ARRAY['id', 'guid', 'model_id', 'model_guid', 'model_name', 'entity_type', 'display_id', 'name', 'description',
                 'parent_entity_id', 'parent_name', 'status', 'created_at', 'created_by',
                 'modified_at', 'modified_by', 'row_version']
$$;

-- A table name given by the caller: lower-case letters, digits and underscores, starting with a
-- letter or underscore, short enough for the "_rel" table (PostgreSQL names are at most 63 bytes).
CREATE FUNCTION eax._check_table_name(p_table text) RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF p_table IS NULL OR trim(p_table) = '' THEN
        RAISE EXCEPTION 'Give a name for the temporary table, for example get_entity(''Application Component'', ''apps'')'
            USING HINT = 'Code should use a fresh name for every call, for example ''e_'' || replace(gen_random_uuid()::text, ''-'', '''').';
    END IF;
    IF p_table !~ '^[a-z_][a-z0-9_]{0,58}$' THEN
        RAISE EXCEPTION 'Table name "%" must be lower-case letters, digits and underscores (at most 59), starting with a letter or underscore', p_table;
    END IF;
    RETURN p_table;
END;
$$;

CREATE FUNCTION eax._load_entity(
    p_type               text,
    p_table              text,    -- name of the entity table; the relationship table is <name>_rel
    p_model              uuid,    -- the model's guid, or NULL for every readable model
    p_name               text,
    p_with_relationships boolean
) RETURNS text[] LANGUAGE plpgsql AS $$
DECLARE
    v_types     bigint[];
    v_table     text := eax._check_table_name(p_table);
    v_rel_table text;
    v_cols      text := '';
    v_col       text;
    r           record;
BEGIN
    IF p_type IS NULL OR trim(p_type) = '' THEN
        RAISE EXCEPTION 'Give an entity type, for example get_entity(''Application Component'')';
    END IF;

    -- 1. The entity type, by code, name or table name, in every readable model (or one model)
    SELECT array_agg(et.id)
      INTO v_types
      FROM core.entity_types et
      JOIN core.models m ON m.id = et.model_id
     WHERE NOT et.is_deleted AND NOT m.is_deleted
       AND (p_model IS NULL OR m.guid = p_model)
       AND core.can_read_model(et.model_id)
       AND lower(p_type) IN (lower(et.code), lower(et.name), lower(et.table_name));
    IF v_types IS NULL THEN
        RAISE EXCEPTION 'No entity type "%"%', p_type,
            CASE WHEN p_model IS NULL THEN '' ELSE ' in that model' END
            USING HINT = 'Use the type''s name (Application Component), code (ApplicationComponent) or table name (application_component).';
    END IF;

    v_rel_table := v_table || '_rel';
    IF to_regclass('pg_temp.' || v_table) IS NOT NULL
       OR (p_with_relationships AND to_regclass('pg_temp.' || v_rel_table) IS NOT NULL) THEN
        RAISE EXCEPTION 'A temporary table "%" already exists in this session', v_table
            USING HINT = 'Use another name, or drop the old one first: SELECT eax.drop_entity(''' || v_table || ''').';
    END IF;

    -- 2. One column per attribute that applies to the type, typed by the attribute's data type
    FOR r IN
        SELECT at.column_name,
               min(dt.storage)  AS storage,
               min(dt.sql_type) AS sql_type,
               min(ia.sort_order) AS sort_order,
               array_agg(DISTINCT at.id) AS attr_ids
          FROM core.item_attributes ia
          JOIN core.attribute_types at ON at.id = ia.attribute_type_id AND NOT at.is_deleted
          JOIN core.data_types dt ON dt.code = at.data_type_code
         WHERE ia.entity_type_id = ANY (v_types) AND NOT ia.is_deleted
         GROUP BY at.column_name
         ORDER BY min(ia.sort_order), at.column_name
    LOOP
        v_col := CASE WHEN r.column_name = ANY (eax._reserved_columns())
                      THEN r.column_name || '_attr' ELSE r.column_name END;
        IF r.storage = 'ref' THEN
            -- a link to another entity: its name, plus its id in <column>_id
            v_cols := v_cols || format(
                ', (array_agg(re.name) FILTER (WHERE av.attribute_type_id = ANY (%L::bigint[])))[1] AS %I'
                ', (array_agg(av.value_ref) FILTER (WHERE av.attribute_type_id = ANY (%L::bigint[])))[1] AS %I',
                r.attr_ids, v_col, r.attr_ids, v_col || '_id');
        ELSE
            v_cols := v_cols || format(
                ', ((array_agg(av.%I) FILTER (WHERE av.attribute_type_id = ANY (%L::bigint[])))[1])::%s AS %I',
                CASE r.storage WHEN 'text' THEN 'value_text' WHEN 'number' THEN 'value_number'
                               WHEN 'date' THEN 'value_date' ELSE 'value_bool' END,
                r.attr_ids, r.sql_type, v_col);
        END IF;
    END LOOP;

    -- 3. The entity table
    EXECUTE format($sql$
        CREATE TEMP TABLE %I ON COMMIT PRESERVE ROWS AS
        SELECT e.id, e.guid, e.model_id, m.guid AS model_guid, m.name AS model_name, et.name AS entity_type,
               e.display_id, e.name, e.description,
               e.parent_entity_id, pe.name AS parent_name,
               e.status_code AS status %s,
               e.created_at, e.created_by, e.modified_at, e.modified_by, e.row_version
          FROM core.entities e
          JOIN core.models m        ON m.id = e.model_id
          JOIN core.entity_types et ON et.id = e.entity_type_id
          LEFT JOIN core.entities pe ON pe.id = e.parent_entity_id
          LEFT JOIN core.attribute_values av ON av.entity_id = e.id AND NOT av.is_deleted
          LEFT JOIN core.entities re ON re.id = av.value_ref
         WHERE e.entity_type_id = ANY (%L::bigint[])
           AND NOT e.is_deleted
           AND core.can_read_model(e.model_id)
           AND (%L::text IS NULL OR lower(e.name) = lower(%L::text))
         GROUP BY e.id, m.guid, m.name, et.name, pe.name
         ORDER BY m.name, e.display_id
        $sql$, v_table, v_cols, v_types, p_name, p_name);

    IF NOT p_with_relationships THEN
        RETURN ARRAY[v_table];
    END IF;

    -- 4. The relationship table: one row per relationship end, outgoing and incoming
    EXECUTE format($sql$
        CREATE TEMP TABLE %I ON COMMIT PRESERVE ROWS AS
        SELECT x.id AS entity_id, x.guid AS entity_guid, x.name AS entity_name,
               r.id AS relationship_id, r.guid AS relationship_guid, rt.name AS relationship_type, rt.verb,
               d.direction,
               o.id AS other_entity_id, o.guid AS other_entity_guid, oet.name AS other_entity_type,
               o.display_id AS other_display_id, o.name AS other_entity_name,
               r.name AS relationship_name, r.status_code AS status,
               (SELECT coalesce(jsonb_object_agg(at.code, coalesce(
                           to_jsonb(av.value_text), to_jsonb(av.value_number), to_jsonb(av.value_date),
                           to_jsonb(av.value_bool), to_jsonb(av.value_ref))), '{}'::jsonb)
                  FROM core.attribute_values av
                  JOIN core.attribute_types at ON at.id = av.attribute_type_id
                 WHERE av.relationship_id = r.id AND NOT av.is_deleted) AS attributes
          FROM pg_temp.%I x
          JOIN core.relationships r
            ON (r.source_entity_id = x.id OR r.target_entity_id = x.id) AND NOT r.is_deleted
          JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
          CROSS JOIN LATERAL (
                SELECT 'outgoing'::text AS direction, r.target_entity_id AS other_id WHERE r.source_entity_id = x.id
                UNION ALL
                SELECT 'incoming', r.source_entity_id WHERE r.target_entity_id = x.id) d
          JOIN core.entities o        ON o.id = d.other_id AND NOT o.is_deleted
          JOIN core.entity_types oet ON oet.id = o.entity_type_id
         ORDER BY x.name, d.direction DESC, rt.name, o.name
        $sql$, v_rel_table, v_table);

    RETURN ARRAY[v_table, v_rel_table];
END;
$$;

-- Every entity of a type (optionally in one model), with their relationships, into tables you name.
CREATE FUNCTION eax.get_entity(
    p_type               text,
    p_table              text,
    p_model              uuid    DEFAULT NULL,
    p_with_relationships boolean DEFAULT true
) RETURNS text[] LANGUAGE sql AS $$
    SELECT eax._load_entity(p_type, p_table, p_model, NULL, p_with_relationships)
$$;

-- One named entity of a type (the name may occur in several models: one row each).
CREATE FUNCTION eax.get_entity_by_name(
    p_type               text,
    p_name               text,
    p_table              text,
    p_model              uuid    DEFAULT NULL,
    p_with_relationships boolean DEFAULT true
) RETURNS text[] LANGUAGE sql AS $$
    SELECT eax._load_entity(p_type, p_table, p_model, p_name, p_with_relationships)
$$;

-- Drops the tables of an earlier get_entity call in this session (both, if they exist).
CREATE FUNCTION eax.drop_entity(p_table text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_table text := eax._check_table_name(p_table);
BEGIN
    IF to_regclass('pg_temp.' || v_table || '_rel') IS NOT NULL THEN
        EXECUTE format('DROP TABLE pg_temp.%I', v_table || '_rel');
    END IF;
    IF to_regclass('pg_temp.' || v_table) IS NOT NULL THEN
        EXECUTE format('DROP TABLE pg_temp.%I', v_table);
    END IF;
END;
$$;

COMMENT ON FUNCTION eax.get_entity(text, text, uuid, boolean) IS
    'Builds temporary tables <p_table> (one row per entity, one column per attribute) and <p_table>_rel (its relationships), dropped when the connection closes. Returns their names.';
COMMENT ON FUNCTION eax.get_entity_by_name(text, text, text, uuid, boolean) IS
    'Like get_entity, for one named entity (case-insensitive).';
COMMENT ON FUNCTION eax.drop_entity(text) IS
    'Drops the temporary tables of a get_entity call: <p_table> and <p_table>_rel.';
