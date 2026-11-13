-- =====================================================================================
-- 0061_farm_sites: Sites (R2.1, D646; owner, 13 Nov 2026): one list of EA Explorer sites shared by everyone, in a schema
--   of its own (farm) reached by EAX_FARM_DB_URL (empty = this database), as the other parts that can move (D630).
--   This site (Local) is one row; a site deployed from the Deploy page is added when its deployment finishes. Each row
--   keeps its last health (green, amber, red) from the site's public heartbeat. Only Super Admins change the list (the
--   API checks it). A table and indexes only (D248). No version change.
-- =====================================================================================

CREATE SCHEMA IF NOT EXISTS farm;

CREATE TABLE IF NOT EXISTS farm.sites (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid          uuid        NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    name          text        NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 120),
    url           text        NOT NULL CHECK (url ~ '^https?://' AND length(url) <= 500),
    note          text        NOT NULL DEFAULT '',
    source        text        NOT NULL DEFAULT 'added' CHECK (source IN ('local', 'added', 'deployed')),
    deployment    text,
    health        text        NOT NULL DEFAULT 'unknown' CHECK (health IN ('green', 'amber', 'red', 'unknown')),
    health_detail text        NOT NULL DEFAULT '',
    version       text        NOT NULL DEFAULT '',
    checked_at    timestamptz,
    created_by    text        NOT NULL DEFAULT 'system',
    created_at    timestamptz NOT NULL DEFAULT now(),
    modified_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS sites_name ON farm.sites (lower(name));
CREATE UNIQUE INDEX IF NOT EXISTS sites_url ON farm.sites (lower(url));
CREATE UNIQUE INDEX IF NOT EXISTS sites_one_local ON farm.sites (source) WHERE source = 'local';
COMMENT ON TABLE farm.sites IS 'R2.1: the EA Explorer sites everyone sees in the site picker; EAX_FARM_DB_URL';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_app') THEN
        GRANT USAGE ON SCHEMA farm TO eax_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON farm.sites TO eax_app;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT USAGE ON SCHEMA farm TO eax_migrator;
        GRANT SELECT, INSERT, UPDATE, DELETE ON farm.sites TO eax_migrator;
    END IF;
END;
$$;
