-- =====================================================================================
-- 0063_foreign_key_indexes: every foreign key has an index (R2.24 part 4, D648; owner, 13 Nov 2026: "Index everything
--   as you see fit"; "There will never be cross DB or cross schema foreign keys"). Deleting a model or a project (purge,
--   archive, the self-test's clean-up at every run's end) checks every table that points at it; without an index each
--   check reads the whole child table. Indexes only (D248): this block runs once, here, and keeps nothing.
--   * each foreign key's columns, in order; a column that may be empty gets a partial index (WHERE ... IS NOT NULL)
--   * left out on purpose: status_code on the five busiest tables (entities, relationships, attribute_values,
--     allowed_relationships, item_attributes): a lookup of a few values whose rows are never deleted, so the index would
--     only slow every write there (eax/testing/db_checks.py FK_INDEX_EXCEPTIONS, the same list)
--   * the library models' copies of the content tables (library_models.*, D633, no foreign keys of their own) get the
--     same indexes as their core tables, so reading a library model is as fast as reading any other
-- =====================================================================================
DO $$
DECLARE
    fk record;
    cols text;
    nullable boolean;
    idx text;
    lib text;
BEGIN
    FOR fk IN
        SELECT c.conrelid, n.nspname AS sch, t.relname AS tbl, c.conkey,
               array_agg(a.attname ORDER BY k.ord) AS names,
               bool_or(NOT a.attnotnull) AS any_null
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
          JOIN pg_namespace n ON n.oid = t.relnamespace
          CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
         WHERE c.contype = 'f'
           AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'procrastinate')
           AND NOT EXISTS (SELECT 1 FROM pg_index i
                            WHERE i.indrelid = c.conrelid
                              AND (i.indkey::int2[])[0:array_length(c.conkey, 1) - 1] @> c.conkey
                              AND (i.indkey::int2[])[0:array_length(c.conkey, 1) - 1] <@ c.conkey)
         GROUP BY c.oid, c.conrelid, n.nspname, t.relname, c.conkey
    LOOP
        IF fk.sch = 'core' AND fk.tbl IN ('entities', 'relationships', 'attribute_values', 'allowed_relationships',
                                          'item_attributes') AND fk.names = ARRAY['status_code']::name[] THEN
            CONTINUE;
        END IF;
        cols := array_to_string(ARRAY(SELECT quote_ident(x) FROM unnest(fk.names) x), ', ');
        idx := left(fk.tbl || '_' || array_to_string(fk.names, '_'), 55) || '_fk';
        nullable := fk.any_null;
        BEGIN
            EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I.%I (%s)%s', idx, fk.sch, fk.tbl, cols,
                           CASE WHEN nullable THEN format(' WHERE %s IS NOT NULL',
                                array_to_string(ARRAY(SELECT quote_ident(x) || ' IS NOT NULL' FROM unnest(fk.names) x), ' AND '))
                                ELSE '' END);
            -- the library models' copy of a core content table, when there is one
            IF fk.sch = 'core' AND to_regclass('library_models.' || quote_ident(fk.tbl)) IS NOT NULL THEN
                lib := left('lib_' || idx, 63);
                EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON library_models.%I (%s)%s', lib, fk.tbl, cols,
                               CASE WHEN nullable THEN format(' WHERE %s IS NOT NULL',
                                    array_to_string(ARRAY(SELECT quote_ident(x) || ' IS NOT NULL' FROM unnest(fk.names) x), ' AND '))
                                    ELSE '' END);
            END IF;
        EXCEPTION WHEN insufficient_privilege OR undefined_column THEN
            RAISE NOTICE 'foreign key index skipped on %.% (%): %', fk.sch, fk.tbl, cols, SQLERRM;
        END;
    END LOOP;
END;
$$;
