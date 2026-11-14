-- Faster text comparisons (R3.7, D665; owner, 12 Nov 2026: "if we do where on strings then those need to be 1. converted
-- into str_md5 2. indexed on this new col 3. Used in search"; decided 13 Nov 2026: exact matches through a hash with its
-- index, "contains" through trigram indexes). Indexes only: no logic in the database (D248).

-- exact matches on a name (any length, case ignored): the md5 of lower(name) as a uuid (16 bytes), indexed; the query
-- compares the key and then the name itself
CREATE INDEX IF NOT EXISTS entities_name_key_idx ON core.entities (model_id, (md5(lower(name))::uuid)) WHERE NOT is_deleted;
-- an exact attribute value (long text too)
CREATE INDEX IF NOT EXISTS attribute_values_value_key_idx ON core.attribute_values (attribute_type_id, (md5(value_text)::uuid))
    WHERE NOT is_deleted AND value_text IS NOT NULL;
-- a display id typed in any case
CREATE INDEX IF NOT EXISTS entities_display_id_lower_idx ON core.entities (model_id, lower(display_id)) WHERE NOT is_deleted;

-- "contains" (Find, search, filters): every column a search ORs with the name has its own trigram index, so the
-- search uses the indexes together instead of reading the whole table
CREATE INDEX IF NOT EXISTS entities_display_id_trgm_idx ON core.entities USING gin (display_id gin_trgm_ops) WHERE NOT is_deleted;
CREATE INDEX IF NOT EXISTS entities_description_trgm_idx ON core.entities USING gin (description gin_trgm_ops) WHERE NOT is_deleted;
CREATE INDEX IF NOT EXISTS entity_aliases_old_name_trgm_idx ON core.entity_aliases USING gin (old_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS entity_aliases_old_display_id_trgm_idx ON core.entity_aliases USING gin (old_display_id gin_trgm_ops);
