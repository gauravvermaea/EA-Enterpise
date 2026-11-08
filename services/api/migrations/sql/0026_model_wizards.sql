-- =====================================================================================
-- 0026_model_wizards: build phase 13.0.4 (version 0.14.4), model wizards (D283)
--   * a frozen model: read only for good (its lock stays 'content'); only a Super Admin unfreezes it. A lock is
--     temporary and is lifted by a Model Admin; a freeze is final
-- Rows only: the rules are in eax/model_wizards.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.14.4', '0026_model_wizards', 'Phase 13.0.4: model wizards (copy, merge and propagate with selection, freeze, split, duplicates...)');

ALTER TABLE core.models
    ADD COLUMN frozen_at   timestamptz,
    ADD COLUMN frozen_by   text,
    ADD COLUMN frozen_note text NOT NULL DEFAULT '';
