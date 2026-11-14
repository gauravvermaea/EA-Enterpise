-- Data discovery and ingestion (the Release 3 epic, D670; owner, 13 Nov 2026: "what I want for Data ingestion is a
-- reverse OData feed: it discovers and then writes to a model"). An import source (phase 34) may now also be an OData
-- feed EA Explorer reads, an endpoint other systems push to, or an AI reading documents; each run of it becomes a
-- delivery, previewed and accepted or declined as every delivery is. Tables, columns and constraints only (D248).

ALTER TABLE core.import_sources
    ADD COLUMN IF NOT EXISTS kind        text NOT NULL DEFAULT 'folder' CHECK (kind IN ('folder', 'odata', 'push', 'ai')),
    ADD COLUMN IF NOT EXISTS url         text NOT NULL DEFAULT '' CHECK (length(url) <= 2000),
    -- the name of a setting in the config file made for it (EAX_SOURCE_...) holding the Authorization header's value:
    -- never the secret itself, and never another setting of the installation (R3.12, D671)
    ADD COLUMN IF NOT EXISTS auth_ref    text NOT NULL DEFAULT '' CHECK (auth_ref = '' OR auth_ref ~ '^EAX_SOURCE_[A-Z0-9_]{1,53}$'),
    ADD COLUMN IF NOT EXISTS mapping     jsonb NOT NULL DEFAULT '{}'::jsonb,   -- each set found: its type, key, name, fields
    ADD COLUMN IF NOT EXISTS schedule    text NOT NULL DEFAULT 'off' CHECK (schedule IN ('off', 'daily', 'weekly')),
    ADD COLUMN IF NOT EXISTS next_run_at timestamptz,
    ADD COLUMN IF NOT EXISTS last_run    jsonb NOT NULL DEFAULT '{}'::jsonb;   -- when, by whom, counts, the matches to confirm
CREATE INDEX IF NOT EXISTS import_sources_due_idx ON core.import_sources (next_run_at) WHERE schedule <> 'off';

ALTER TABLE core.loads DROP CONSTRAINT IF EXISTS loads_delivery_check;
ALTER TABLE core.loads ADD CONSTRAINT loads_delivery_check
    CHECK (delivery IN ('upload', 'folder', 'api', 'odata', 'push', 'ai'));

-- what each source delivered last, by its own key: the next run proposes only what changed
CREATE TABLE IF NOT EXISTS core.discovery_seen (
    source_id  bigint NOT NULL REFERENCES core.import_sources (id) ON DELETE CASCADE,
    set_name   text NOT NULL CHECK (length(set_name) <= 200),
    ext_key    text NOT NULL CHECK (length(ext_key) <= 500),
    hash       text NOT NULL CHECK (hash ~ '^[0-9a-f]{64}$'),
    name       text NOT NULL DEFAULT '',
    seen_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, set_name, ext_key)
);
COMMENT ON TABLE core.discovery_seen IS 'R3 epic (D670): what a discovery source delivered last, so a run proposes only changes';

-- a person's answer to "is this the same as that element?": the next runs deliver it under the element's own name
CREATE TABLE IF NOT EXISTS core.discovery_matches (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id    bigint NOT NULL REFERENCES core.import_sources (id) ON DELETE CASCADE,
    entity_type  text NOT NULL CHECK (length(entity_type) <= 120),
    found_name   text NOT NULL CHECK (btrim(found_name) <> '' AND length(found_name) <= 500),
    decision     text NOT NULL CHECK (decision IN ('same', 'new')),
    entity_guid  uuid,
    confidence   integer CHECK (confidence BETWEEN 0 AND 100),
    decided_by   text NOT NULL,
    decided_at   timestamptz NOT NULL DEFAULT now(),
    CHECK ((decision = 'same') = (entity_guid IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS discovery_matches_found_uq ON core.discovery_matches (source_id, entity_type, lower(found_name));
COMMENT ON TABLE core.discovery_matches IS 'R3 epic (D670): a found item confirmed as an existing element, or as new';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.discovery_seen, core.discovery_matches TO eax_app;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.discovery_seen, core.discovery_matches TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
END;
$$;
