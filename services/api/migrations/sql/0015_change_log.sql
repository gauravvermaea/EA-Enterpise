-- =====================================================================================
-- 0015_change_log: build phase 9 (version 0.9.0), the change log (D180)
--   The change log lives in a database of its own (EAX_CHANGELOG_DB_URL; empty = this database, schema
--   "changelog"), so logging never slows the repository. It is filled from what the repository writes anyway:
--   history.row_versions (every change of content, metamodel and models) and audit.events (the API's actions).
--   eax/change_log.py ships new rows across in the background and creates its own tables there.
--   Here only: the transaction of every history and audit row, so rows are shipped once a transaction has
--   finished and none is missed (a transaction that started earlier may finish later).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.9.0', '0015_change_log', 'Phase 9: the change log (its own database), the transaction of every history and audit row');

ALTER TABLE history.row_versions ADD COLUMN tx bigint NOT NULL DEFAULT txid_current();
CREATE INDEX row_versions_tx_idx ON history.row_versions (tx, id);
ALTER TABLE audit.events ADD COLUMN tx bigint NOT NULL DEFAULT txid_current();
CREATE INDEX events_tx_idx ON audit.events (tx, id);
-- the commit a change came in with (owner, 5 Nov 2026, D195): history rows and the change log show its number and message
ALTER TABLE core.commits ADD COLUMN tx bigint NOT NULL DEFAULT txid_current();
CREATE INDEX commits_tx_idx ON core.commits (tx);
