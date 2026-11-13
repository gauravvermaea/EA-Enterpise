-- =====================================================================================
-- 0065_model_ancestors_concurrency: two models made at the same moment no longer collide (fixed 13 Nov 2026; the
--   owner's full test: "duplicate key value violates unique constraint model_ancestors_pkey", the self-test making its
--   models while the sample data and industry packs were still loading after a clean restart). The statement trigger
--   rebuilds core.model_ancestors whole; two transactions doing so at once both deleted the old rows and inserted the
--   same new ones, and the second to commit failed. The rebuild now waits its turn (a transaction-level advisory
--   lock), so it sees what the first committed, and skips a pair already there. Same function, same trigger (D60).
-- =====================================================================================
CREATE OR REPLACE FUNCTION core.refresh_model_ancestors() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_before text := coalesce(current_setting('eax.rls_bypass', true), '');
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('core.model_ancestors'));
    PERFORM set_config('eax.rls_bypass', 'on', true);
    DELETE FROM core.model_ancestors;
    INSERT INTO core.model_ancestors (model_id, ancestor_id)
    WITH RECURSIVE up (model_id, ancestor_id) AS (
        SELECT id, a FROM core.models, unnest(ARRAY[parent_model_id, source_model_id]) a WHERE a IS NOT NULL
        UNION
        SELECT up.model_id, a FROM up JOIN core.models m ON m.id = up.ancestor_id,
               unnest(ARRAY[m.parent_model_id, m.source_model_id]) a
         WHERE a IS NOT NULL AND a <> up.model_id
    )
    SELECT DISTINCT model_id, ancestor_id FROM up
    ON CONFLICT (model_id, ancestor_id) DO NOTHING;
    PERFORM set_config('eax.rls_bypass', v_before, true);
    RETURN NULL;
END;
$$;
