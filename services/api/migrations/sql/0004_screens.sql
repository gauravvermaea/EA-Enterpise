-- =====================================================================================
-- EA Explorer 0.2.1: model screens after phase 2 (graph kinds, draw.io export of every graph,
-- the entity timeline with values as they were, model and lineage on the entity page, CSV on every
-- page). No schema change: the screens read what phases 1 and 2 already store (history.row_versions,
-- origin_guid, source_model_id). The version moves so the API and the database stay in step (D44).
-- Run by Alembic (migrations/versions/0004_screens.py).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.2.1', '0004_screens', 'Phase 2 additions: graph kinds, draw.io export, entity timeline and lineage (no schema change)');
