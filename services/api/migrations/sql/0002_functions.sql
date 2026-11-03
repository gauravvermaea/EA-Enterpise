-- =====================================================================================
-- EA Explorer phase 1: get_entity and get_entity_by_name
--
-- The repository stores content generically (one entity table, one attribute value table).
-- These functions turn it back into one ordinary table per entity type, built on demand from
-- the current metamodel, plus a table of each entity's relationships:
--
--   SELECT eax.get_entity('Application Component');
--       -> {tmp_application_component, tmp_application_component_rel}
--   SELECT * FROM tmp_application_component WHERE lifecycle = 'Production';
--   SELECT * FROM tmp_application_component_rel WHERE relationship_type = 'Realization';
--
--   SELECT eax.get_entity_by_name('Application Component', 'Claims Platform');
--
-- The tables are temporary: private to the caller's database session and dropped when it
-- ends. A second call for the same type replaces them; pass p_table to keep several sets.
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

CREATE FUNCTION eax._load_entity(
    p_type               text,
    p_model              uuid,    -- the model's guid, or NULL for every readable model
    p_name               text,
    p_with_relationships boolean,
    p_table              text
) RETURNS text[] LANGUAGE plpgsql AS $$
DECLARE
    v_types     bigint[];
    v_base      text;
    v_table     text;
    v_rel_table text;
    v_cols      text := '';
    v_col       text;
    r           record;
BEGIN
    IF p_type IS NULL OR trim(p_type) = '' THEN
        RAISE EXCEPTION 'Give an entity type, for example get_entity(''Application Component'')';
    END IF;

    -- 1. The entity type, by code, name or table name, in every readable model (or one model)
    SELECT array_agg(et.id), min(et.table_name)
      INTO v_types, v_base
      FROM core.entity_type et
      JOIN core.model m ON m.id = et.model_id
     WHERE NOT et.is_deleted AND NOT m.is_deleted
       AND (p_model IS NULL OR m.guid = p_model)
       AND core.can_read_model(et.model_id)
       AND lower(p_type) IN (lower(et.code), lower(et.name), lower(et.table_name));
    IF v_types IS NULL THEN
        RAISE EXCEPTION 'No entity type "%"%', p_type,
            CASE WHEN p_model IS NULL THEN '' ELSE ' in that model' END
            USING HINT = 'Use the type''s name (Application Component), code (ApplicationComponent) or table name (application_component).';
    END IF;

    v_table := 'tmp_' || coalesce(nullif(lower(p_table), ''), v_base);
    IF v_table !~ '^tmp_[a-z][a-z0-9_]{0,55}$' THEN
        RAISE EXCEPTION 'Table name "%" must be lower-case letters, digits and underscores', p_table;
    END IF;
    v_rel_table := v_table || '_rel';

    -- 2. One column per attribute that applies to the type, typed by the attribute's data type
    FOR r IN
        SELECT at.column_name,
               min(dt.storage)  AS storage,
               min(dt.sql_type) AS sql_type,
               min(ia.sort_order) AS sort_order,
               array_agg(DISTINCT at.id) AS attr_ids
          FROM core.item_attribute ia
          JOIN core.attribute_type at ON at.id = ia.attribute_type_id AND NOT at.is_deleted
          JOIN core.data_type dt ON dt.code = at.data_type_code
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
    -- replace the tables of an earlier call in this session (quietly: no notice when absent)
    IF to_regclass('pg_temp.' || v_table) IS NOT NULL THEN
        EXECUTE format('DROP TABLE pg_temp.%I', v_table);
    END IF;
    IF to_regclass('pg_temp.' || v_rel_table) IS NOT NULL THEN
        EXECUTE format('DROP TABLE pg_temp.%I', v_rel_table);
    END IF;
    EXECUTE format($sql$
        CREATE TEMP TABLE %I ON COMMIT PRESERVE ROWS AS
        SELECT e.id, e.guid, e.model_id, m.guid AS model_guid, m.name AS model_name, et.name AS entity_type,
               e.display_id, e.name, e.description,
               e.parent_entity_id, pe.name AS parent_name,
               e.status_code AS status %s,
               e.created_at, e.created_by, e.modified_at, e.modified_by, e.row_version
          FROM core.entity e
          JOIN core.model m        ON m.id = e.model_id
          JOIN core.entity_type et ON et.id = e.entity_type_id
          LEFT JOIN core.entity pe ON pe.id = e.parent_entity_id
          LEFT JOIN core.attribute_value av ON av.entity_id = e.id AND NOT av.is_deleted
          LEFT JOIN core.entity re ON re.id = av.value_ref
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
                  FROM core.attribute_value av
                  JOIN core.attribute_type at ON at.id = av.attribute_type_id
                 WHERE av.relationship_id = r.id AND NOT av.is_deleted) AS attributes
          FROM pg_temp.%I x
          JOIN core.relationship r
            ON (r.source_entity_id = x.id OR r.target_entity_id = x.id) AND NOT r.is_deleted
          JOIN core.relationship_type rt ON rt.id = r.relationship_type_id
          CROSS JOIN LATERAL (
                SELECT 'outgoing'::text AS direction, r.target_entity_id AS other_id WHERE r.source_entity_id = x.id
                UNION ALL
                SELECT 'incoming', r.source_entity_id WHERE r.target_entity_id = x.id) d
          JOIN core.entity o        ON o.id = d.other_id AND NOT o.is_deleted
          JOIN core.entity_type oet ON oet.id = o.entity_type_id
         ORDER BY x.name, d.direction DESC, rt.name, o.name
        $sql$, v_rel_table, v_table);

    RETURN ARRAY[v_table, v_rel_table];
END;
$$;

-- Every entity of a type (optionally in one model), with their relationships.
CREATE FUNCTION eax.get_entity(
    p_type               text,
    p_model              uuid    DEFAULT NULL,
    p_with_relationships boolean DEFAULT true,
    p_table              text    DEFAULT NULL
) RETURNS text[] LANGUAGE sql AS $$
    SELECT eax._load_entity(p_type, p_model, NULL, p_with_relationships, p_table)
$$;

-- One named entity of a type (the name may occur in several models: one row each).
CREATE FUNCTION eax.get_entity_by_name(
    p_type               text,
    p_name               text,
    p_model              uuid    DEFAULT NULL,
    p_with_relationships boolean DEFAULT true,
    p_table              text    DEFAULT NULL
) RETURNS text[] LANGUAGE sql AS $$
    SELECT eax._load_entity(p_type, p_model, p_name, p_with_relationships, p_table)
$$;

COMMENT ON FUNCTION eax.get_entity(text, uuid, boolean, text) IS
    'Builds temporary tables tmp_<type> (one row per entity, one column per attribute) and tmp_<type>_rel (its relationships). Returns their names.';
COMMENT ON FUNCTION eax.get_entity_by_name(text, text, uuid, boolean, text) IS
    'Like get_entity, for one named entity (case-insensitive).';
