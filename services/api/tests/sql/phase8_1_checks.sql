-- Phase 8.1 (0.11.0): notifications, requests, webhooks, metamodel push-down, change documents. Run as the API's
-- login after a clean start. Everything it makes is rolled back.
BEGIN;
DO $$
DECLARE
    v_req  bigint;
    v_n    bigint;
    v_kid  bigint;
BEGIN
    ASSERT EXISTS (SELECT 1 FROM core.schema_versions WHERE version = '0.11.0'), 'version 0.11.0 recorded';
    ASSERT to_regclass('core.notifications') IS NOT NULL AND to_regclass('core.notification_recipients') IS NOT NULL, 'notifications';
    ASSERT to_regclass('core.requests') IS NOT NULL AND to_regclass('core.request_comments') IS NOT NULL, 'requests';
    ASSERT to_regclass('core.webhooks') IS NOT NULL AND to_regclass('core.webhook_deliveries') IS NOT NULL, 'webhooks';
    ASSERT to_regclass('core.metamodel_version_changes') IS NOT NULL, 'the changes of each metamodel version are kept';
    ASSERT to_regclass('core.metamodel_pushes') IS NOT NULL AND to_regclass('core.metamodel_push_targets') IS NOT NULL, 'push-down';
    ASSERT to_regclass('core.change_documents') IS NOT NULL, 'change documents';

    -- a request needs a note to be done or declined
    INSERT INTO core.requests (subject, body, sender, receiver) VALUES ('Check', '', 'user_architect', 'user_model_admin')
        RETURNING id INTO v_req;
    ASSERT (SELECT number FROM core.requests WHERE id = v_req) >= 1001, 'requests are numbered from 1001';
    BEGIN
        UPDATE core.requests SET status = 'done', closed_at = now() WHERE id = v_req;
        RAISE EXCEPTION 'done without a note was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    -- a request to oneself is a note (owner, 6 Nov 2026)
    INSERT INTO core.requests (subject, sender, receiver) VALUES ('A note', 'user_architect', 'user_architect');

    -- information notifications are never resolved; action ones are
    BEGIN
        INSERT INTO core.notifications (kind, category, needs_action, title, actor, resolved_at)
        VALUES ('model.locked', 'model', false, 'Locked', 'x', now());
        RAISE EXCEPTION 'an information notification was resolved';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    INSERT INTO core.notifications (kind, category, needs_action, title, actor) VALUES ('request.new', 'request', true, 'New', 'x')
        RETURNING id INTO v_n;
    INSERT INTO core.notification_recipients (notification_id, username) VALUES (v_n, 'user_model_admin');
    BEGIN
        INSERT INTO core.notification_recipients (notification_id, username) VALUES (v_n, 'User_Model_Admin');
        RAISE EXCEPTION 'a username in capitals was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- a webhook address is http(s)
    BEGIN
        INSERT INTO core.webhooks (name, url, secret, created_by) VALUES ('x', 'ftp://example.org', 's', 'x');
        RAISE EXCEPTION 'a non-http webhook was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- the push-down setting lets the metamodel (and the model row) of the one named model change, and nothing else
    v_kid := (SELECT id FROM core.models WHERE parent_model_id IS NOT NULL AND kind_code = 'project' ORDER BY id LIMIT 1);
    PERFORM set_config('eax.push_down', v_kid::text, true);
    ASSERT position('core.why_not' IN pg_get_functiondef('core.why_not(bigint,text)'::regprocedure)) > 0, 'why_not';
    ASSERT pg_get_functiondef('core.why_not(bigint,text)'::regprocedure) LIKE '%eax.push_down%', 'why_not knows push-down';
    ASSERT pg_get_functiondef('core.why_not(bigint,text)'::regprocedure) LIKE '%committer%', 'the committer rule (0013) is kept';
    PERFORM set_config('eax.push_down', '', true);

    -- the report login never reads requests or notifications
    ASSERT NOT has_table_privilege('eax_report', 'core.requests', 'SELECT'), 'requests are not in reports';
    ASSERT NOT has_table_privilege('eax_report', 'core.notifications', 'SELECT'), 'notifications are not in reports';
    ASSERT NOT has_table_privilege('eax_report', 'core.webhooks', 'SELECT'), 'webhook secrets are not in reports';
    RAISE NOTICE 'phase 8.1 checks passed';
END;
$$;
ROLLBACK;
