-- =====================================================================================
-- 0042_import_formats: version 0.18.0, published import formats and deliveries (phase 34 and 34.1, D370, D378, D385,
-- D462 to D467)
--   * an import source: another system that delivers data to one model in the published formats (Excel, the CSV
--     format with its master file). Its deliveries arrive in its own folder under the API's import folder
--     (deliveries/<model>/<folder>/incoming, which IT may map or mount to SFTP or a share), are uploaded in the screens
--     or sent to the API by a service account. values_win: the source's values win over values changed in EA Explorer
--     for the fields it delivers; otherwise only empty fields are filled and differences are shown (D464)
--   * a load may come from a source (a delivery): how it came, who sent it, and the person who accepted it as their
--     committed load or declined it
-- Rows only: matching by type and name, never deleting, which values win and who may accept are in eax/deliveries.py
-- and eax/loads.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.18.0', '0042_import_formats', 'Batch 2 (D421): published import formats and deliveries; a model from a metamodel workbook')
ON CONFLICT (version) DO NOTHING;   -- several 0.18.0 migrations (batch 2): the first one writes the version

CREATE TABLE core.import_sources (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_id     bigint NOT NULL REFERENCES core.models (id) ON DELETE CASCADE,
    name         text NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 120),
    description  text NOT NULL DEFAULT '' CHECK (length(description) <= 2000),
    folder       text NOT NULL CHECK (folder ~ '^[a-z0-9][a-z0-9_-]{0,59}$'),   -- deliveries/<model guid>/<folder>/
    values_win   boolean NOT NULL DEFAULT false,
    contact      text NOT NULL CHECK (contact = lower(contact)),               -- who is told when a delivery waits
    sender       text CHECK (sender IS NULL OR sender = lower(sender)),        -- the service account that sends it, if any
    active       boolean NOT NULL DEFAULT true,
    created_by   text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    last_delivery_at timestamptz,
    UNIQUE (model_id, folder)
);
CREATE UNIQUE INDEX import_sources_name ON core.import_sources (model_id, lower(name));
COMMENT ON TABLE core.import_sources IS 'Phase 34: another system that delivers data to a model in the published formats (D370)';

ALTER TABLE core.loads
    ADD COLUMN IF NOT EXISTS source_id   bigint REFERENCES core.import_sources (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS delivery    text NOT NULL DEFAULT 'upload' CHECK (delivery IN ('upload', 'folder', 'api')),
    ADD COLUMN IF NOT EXISTS accepted_by text,
    ADD COLUMN IF NOT EXISTS accepted_at timestamptz,
    ADD COLUMN IF NOT EXISTS declined_by text,
    ADD COLUMN IF NOT EXISTS declined_at timestamptz;
ALTER TABLE core.loads DROP CONSTRAINT IF EXISTS loads_status_check;
ALTER TABLE core.loads ADD CONSTRAINT loads_status_check
    CHECK (status IN ('uploaded', 'mapping', 'previewed', 'added', 'undone', 'failed', 'declined'));
CREATE INDEX IF NOT EXISTS loads_source_idx ON core.loads (source_id, created_at DESC) WHERE source_id IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.import_sources TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
END;
$$;
