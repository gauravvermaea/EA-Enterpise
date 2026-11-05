-- Phase 9 database checks: the change log (D180) lives in its own database; here only what the repository adds for it.
-- Run as the API's login:
--   Get-Content services/api/tests/sql/phase9_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
-- Runs in one transaction that is rolled back. Ends with "phase 9 checks passed".
BEGIN;

DO $$
DECLARE
    v_model  bigint;
    v_entity bigint;
    v_guid   uuid;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM core.schema_versions WHERE version = '0.9.0') THEN
        RAISE EXCEPTION 'schema version 0.9.0 (0015_change_log) is missing';
    END IF;
    ASSERT to_regclass('core.change_log') IS NULL, 'the change log is not in the repository (its own database, D180)';
    ASSERT to_regclass('history.row_versions_tx_idx') IS NOT NULL AND to_regclass('audit.events_tx_idx') IS NOT NULL, 'the tx indexes';

    PERFORM set_config('eax.rls_bypass', 'on', true);
    SELECT id INTO v_model FROM core.models WHERE name = 'Protea Insurance (demo estate)';
    SELECT e.id, e.guid INTO v_entity, v_guid FROM core.entities e WHERE e.model_id = v_model AND NOT e.is_deleted ORDER BY e.id LIMIT 1;
    ASSERT v_entity IS NOT NULL, 'the demo estate is loaded';

    -- every history row and audit event carries the transaction that wrote it (the shipper waits for it to finish)
    PERFORM set_config('eax.actor', 'check_user', true);
    UPDATE core.entities SET description = 'Changed by the phase 9 check' WHERE id = v_entity;
    ASSERT (SELECT tx FROM history.row_versions WHERE row_guid = v_guid ORDER BY id DESC LIMIT 1) = txid_current(), 'history tx';
    INSERT INTO audit.events (actor, action, object_type, object_id, details) VALUES ('check_user', 'tag.create', 'model', '', '{}');
    ASSERT (SELECT tx FROM audit.events ORDER BY id DESC LIMIT 1) = txid_current(), 'audit tx';
    ASSERT pg_snapshot_xmin(pg_current_snapshot())::text::bigint <= txid_current(), 'this transaction is not shipped yet';
END $$;

SELECT 'phase 9 checks passed' AS result;
ROLLBACK;
