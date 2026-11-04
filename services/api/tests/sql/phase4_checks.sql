-- Phase 4 database checks: creating and copying models, the library (Library Admin, D118), deleting
-- (Super Admin, refused while other models depend on it, D121) and metamodel drafts (D115).
-- Run as the API's login (it owns the tables, so row-level security applies to it):
--   Get-Content services/api/tests/sql/phase4_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
-- Runs in one transaction that is rolled back. Ends with "phase 4 checks passed".
BEGIN;

CREATE FUNCTION pg_temp.expect_error(p_sql text, p_fragment text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE p_sql;
    EXCEPTION WHEN OTHERS THEN
        IF position(p_fragment IN SQLERRM) = 0 THEN
            RAISE EXCEPTION 'expected an error containing "%", got: %', p_fragment, SQLERRM;
        END IF;
        RETURN;
    END;
    RAISE EXCEPTION 'expected an error containing "%", but the statement succeeded', p_fragment;
END $$;
CREATE FUNCTION pg_temp.as_user(p_user text, p_roles text) RETURNS void LANGUAGE sql AS $$
    SELECT set_config('eax.actor', p_user, true), set_config('eax.user_roles', p_roles, true)
$$;
CREATE FUNCTION pg_temp.m(p_name text) RETURNS bigint LANGUAGE sql AS $$
    SELECT id FROM core.models WHERE name = p_name AND NOT is_deleted
$$;

DO $$
DECLARE
    v_root bigint;
    v_ref  bigint;
    v_new  bigint;
    v_out  jsonb;
BEGIN
    ASSERT string_to_array(core.schema_version(), '.')::int[] >= ARRAY[0, 4, 0], 'database version 0.4.0 or later';
    ASSERT EXISTS (SELECT 1 FROM core.app_roles WHERE code = 'library-admin' AND scope = 'global'), 'the Library Admin role';
    ASSERT NOT EXISTS (SELECT 1 FROM core.models WHERE kind_code IN ('template', 'reference') AND library_state = ''),
        'every root and reference model has a library state';
    ASSERT NOT EXISTS (SELECT 1 FROM core.models WHERE kind_code = 'project' AND library_state <> ''),
        'working models have none';
    ASSERT (SELECT library_state FROM core.models WHERE name = 'ArchiMate 4') = 'published', 'shipped roots are published';

    -- a Model Creator builds a root of their own (it starts as building, unlocked)
    PERFORM pg_temp.as_user('check_creator', 'model-creator');
    INSERT INTO core.models (name, kind_code, source_model_id, metamodel_name)
    VALUES ('Check root', 'template', (SELECT id FROM core.models WHERE kind_code = 'template' AND source_model_id IS NULL), 'Check')
    RETURNING id INTO v_root;
    ASSERT (SELECT library_state FROM core.models WHERE id = v_root) = 'building', 'a new root starts as building';
    ASSERT EXISTS (SELECT 1 FROM core.models WHERE id = v_root), 'whoever created a model sees it at once';
    ASSERT core.model_roles(v_root) @> ARRAY['model-admin'], 'its creator is its Model Admin';

    -- copy ArchiMate's metamodel into it (as the model service does)
    v_out := core.copy_model(pg_temp.m('ArchiMate 4'), v_root, false);
    ASSERT (v_out ->> 'entity_types')::int = (SELECT count(*) FROM core.entity_types WHERE model_id = pg_temp.m('ArchiMate 4')),
        'copy_model copies every entity type';
    ASSERT (SELECT count(*) FROM core.entities WHERE model_id = v_root) = 0, 'a metamodel copy has no content';

    -- a project model with the content of the insurance reference model: display IDs kept
    INSERT INTO core.models (name, kind_code, source_model_id, metamodel_name)
    VALUES ('Check project', 'project', pg_temp.m('Insurance reference model'), 'ArchiMate 4') RETURNING id INTO v_new;
    v_out := core.copy_model(pg_temp.m('Insurance reference model'), v_new, true);
    ASSERT (SELECT count(*) FROM core.entities WHERE model_id = v_new AND NOT is_deleted)
         = (SELECT count(*) FROM core.entities WHERE model_id = pg_temp.m('Insurance reference model') AND NOT is_deleted),
        'a content copy has every entity';
    ASSERT (SELECT count(*) FROM core.relationships WHERE model_id = v_new AND NOT is_deleted)
         = (SELECT count(*) FROM core.relationships WHERE model_id = pg_temp.m('Insurance reference model') AND NOT is_deleted),
        'and every relationship';
    ASSERT NOT EXISTS (
        SELECT display_id FROM core.entities WHERE model_id = pg_temp.m('Insurance reference model') AND NOT is_deleted
        EXCEPT SELECT display_id FROM core.entities WHERE model_id = v_new AND NOT is_deleted), 'with the same display IDs';
    ASSERT (SELECT copy_state FROM core.models WHERE id = v_new) = '', 'not marked as copying';

    -- not a Library Admin: no reference models, no publishing
    PERFORM pg_temp.as_user('check_creator', 'model-creator');
END $$;

SELECT pg_temp.as_user('check_creator', 'model-creator');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.models (name, kind_code, source_model_id, metamodel_name)
    VALUES ('Check reference', 'reference', (SELECT id FROM core.models WHERE name = 'ArchiMate 4'), 'ArchiMate 4') $q$,
    'reference models are added to the library by a Library Admin');
SELECT pg_temp.expect_error($q$
    UPDATE core.models SET is_locked = true, library_state = 'published' WHERE name = 'Check root' $q$,
    'Only a Library Admin can publish');
SELECT pg_temp.expect_error($q$ UPDATE core.models SET is_deleted = true WHERE name = 'Check project' $q$,
    'deleting a model needs the Super Admin role');

-- a Library Admin creates a reference model, publishes it and withdraws it
DO $$
DECLARE
    v_ref bigint;
BEGIN
    PERFORM pg_temp.as_user('check_librarian', 'library-admin');
    ASSERT core.may_curate_library(), 'a Library Admin curates the library';
    INSERT INTO core.models (name, kind_code, source_model_id, metamodel_name, version_label)
    VALUES ('Check reference', 'reference', pg_temp.m('ArchiMate 4'), 'ArchiMate 4', '0.1') RETURNING id INTO v_ref;
    ASSERT (SELECT library_state FROM core.models WHERE id = v_ref) = 'building', 'a new reference model is building';
    UPDATE core.models SET approval_state = 'requested' WHERE id = v_ref;          -- request, then approve (D134)
    UPDATE core.models SET is_locked = true, library_state = 'published' WHERE id = v_ref;
    ASSERT (SELECT is_locked FROM core.models WHERE id = v_ref), 'published: locked';
    UPDATE core.models SET library_state = 'withdrawn' WHERE id = v_ref;
    ASSERT (SELECT library_state FROM core.models WHERE id = v_ref) = 'withdrawn', 'withdrawn while locked';
    UPDATE core.models SET library_state = 'published' WHERE id = v_ref;
    UPDATE core.models SET approval_state = 'requested' WHERE name = 'Check root';
    UPDATE core.models SET is_locked = true, library_state = 'published' WHERE name = 'Check root';
    ASSERT (SELECT library_state FROM core.models WHERE name = 'Check root') = 'published', 'an own root can be a library model (D119)';
END $$;

-- a Super Admin cannot delete a model others depend on; can delete one nobody depends on
SELECT pg_temp.as_user('check_super', 'super-admin');
SELECT pg_temp.expect_error($q$ UPDATE core.models SET is_deleted = true WHERE name = 'Fynbos Mutual (group)' $q$,
    'cannot be deleted: other models are derived from it or built on it');
DO $$
BEGIN
    PERFORM pg_temp.as_user('check_super', 'super-admin');
    UPDATE core.models SET is_deleted = true WHERE name = 'Check project';
    ASSERT NOT EXISTS (SELECT 1 FROM core.models WHERE name = 'Check project' AND NOT is_deleted), 'deleted';
END $$;

-- metamodel drafts: a draft for changes needs its target; kinds and statuses are checked
SELECT pg_temp.expect_error($q$
    INSERT INTO core.metamodel_drafts (name, kind) VALUES ('Check changes', 'changes') $q$, 'metamodel_drafts_check');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.metamodel_drafts (name, kind, status) VALUES ('Check root draft', 'root', 'maybe') $q$, 'metamodel_drafts_status_check');
DO $$
BEGIN
    INSERT INTO core.metamodel_drafts (name, kind, spec, proposed_via) VALUES ('Check root draft', 'root', '{"format": "eax-metamodel/1"}', 'mcp');
    ASSERT (SELECT status FROM core.metamodel_drafts WHERE name = 'Check root draft') = 'draft', 'a draft waits for review';
END $$;

-- draft models (D131): a person's new model is a draft; others may not create models from it until it is published
DO $$
DECLARE
    v_m bigint;
BEGIN
    ASSERT NOT (SELECT is_draft FROM core.models WHERE name = 'ArchiMate 4'), 'the installer''s models are published';
    PERFORM pg_temp.as_user('check_creator', 'model-creator');
    INSERT INTO core.models (name, kind_code, source_model_id, metamodel_name)
    VALUES ('Check draft', 'project', pg_temp.m('Karoo Re (independent)'), 'ArchiMate 4') RETURNING id INTO v_m;
    ASSERT (SELECT is_draft FROM core.models WHERE id = v_m), 'a new model starts as a draft';
    INSERT INTO core.model_users (model_id, username, role) VALUES (v_m, 'check_reader', 'architect');
    INSERT INTO core.models (name, kind_code, source_model_id, metamodel_name)
    VALUES ('Check own try', 'project', v_m, 'ArchiMate 4');   -- its own Model Admin may
END $$;
SELECT pg_temp.as_user('check_creator', 'model-creator');
SELECT pg_temp.expect_error($q$ UPDATE core.models SET is_draft = false WHERE name = 'Check draft' $q$,
    'request publishing first');
SELECT pg_temp.as_user('check_reader', 'model-creator');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.models (name, kind_code, source_model_id, metamodel_name)
    VALUES ('Check from draft', 'project', (SELECT id FROM core.models WHERE name = 'Check draft'), 'ArchiMate 4') $q$,
    'is a draft: it must be published');
DO $$
BEGIN
    PERFORM pg_temp.as_user('check_creator', 'model-creator');
    UPDATE core.models SET approval_state = 'requested' WHERE name = 'Check draft';   -- request, then approve (D134)
    UPDATE core.models SET is_draft = false WHERE name = 'Check draft';
    ASSERT (SELECT published_by FROM core.models WHERE name = 'Check draft') = 'check_creator', 'publishing stamps who';
    PERFORM pg_temp.as_user('check_reader', 'model-creator');
    INSERT INTO core.models (name, kind_code, source_model_id, metamodel_name)
    VALUES ('Check from published', 'project', (SELECT id FROM core.models WHERE name = 'Check draft'), 'ArchiMate 4');
END $$;
SELECT pg_temp.as_user('check_creator', 'model-creator');
SELECT pg_temp.expect_error($q$ UPDATE core.models SET is_draft = true WHERE name = 'Check draft' $q$, 'cannot go back to draft');

-- metamodel draft review (D130): comments on the draft or an item, rounds, events
DO $$
DECLARE
    v_d bigint;
BEGIN
    INSERT INTO core.metamodel_drafts (name, kind, status, round) VALUES ('Check review', 'root', 'returned', 2) RETURNING id INTO v_d;
    INSERT INTO core.metamodel_draft_comments (draft_id, round, section, item_code, body) VALUES (v_d, 2, 'entity_types', 'Device', 'remove it');
    INSERT INTO core.metamodel_draft_events (draft_id, round, action) VALUES (v_d, 2, 'sent_back');
    ASSERT (SELECT count(*) FROM core.metamodel_draft_comments WHERE draft_id = v_d AND resolved_at IS NULL) = 1, 'an open comment';
END $$;
SELECT pg_temp.expect_error($q$
    INSERT INTO core.metamodel_draft_comments (draft_id, round, section, body)
    SELECT id, 1, 'entity_types', 'x' FROM core.metamodel_drafts WHERE name = 'Check review' $q$, 'metamodel_draft_comments_check');
SELECT pg_temp.expect_error($q$
    INSERT INTO core.metamodel_draft_events (draft_id, round, action)
    SELECT id, 1, 'approved' FROM core.metamodel_drafts WHERE name = 'Check review' $q$, 'metamodel_draft_events_action_check');

SELECT 'phase 4 checks passed' AS result;
ROLLBACK;
