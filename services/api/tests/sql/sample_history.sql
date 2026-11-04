-- Gives "Claims Platform" in the Sample insurance model a history to try the entity timeline on
-- (History tab: click a point to see the values as they were then).
-- Run once as postgres; it CHANGES the sample project model (reference models are locked and are
-- not touched). Each step is its own transaction, a second apart, as a named person.
--   Get-Content services/api/tests/sql/sample_history.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U postgres -d eaexplorer -v ON_ERROR_STOP=1
-- A clean rebuild (eax clean-run) puts the sample model back as it was.

\set ON_ERROR_STOP on
CREATE TEMP VIEW cp AS
SELECT e.id FROM core.entities e JOIN core.models m ON m.id = e.model_id
 WHERE m.name = 'Sample insurance model' AND e.name = 'Claims Platform';

-- 1. Thandi upgrades the platform: version 9.0 -> 9.2
SELECT pg_sleep(1.1), set_config('eax.actor', 'thandi.m', false);
UPDATE core.attribute_values av SET value_text = '9.2'
  FROM core.attribute_types at
 WHERE at.id = av.attribute_type_id AND at.code = 'Version' AND av.entity_id = (SELECT id FROM cp);

-- 2. Pieter updates the cost and the description
SELECT pg_sleep(1.1), set_config('eax.actor', 'pieter.v', false);
UPDATE core.attribute_values av SET value_number = 3350000
  FROM core.attribute_types at
 WHERE at.id = av.attribute_type_id AND at.code = 'AnnualCost' AND av.entity_id = (SELECT id FROM cp);
UPDATE core.entities SET description = 'Claims registration, assessment and settlement (Guidewire ClaimCenter)'
 WHERE id = (SELECT id FROM cp);

-- 3. Thandi removes the link to the claims department (kept in history; put back in step 5)
SELECT pg_sleep(1.1), set_config('eax.actor', 'thandi.m', false);
UPDATE core.relationships r SET is_deleted = true
  FROM core.entities t
 WHERE t.id = r.target_entity_id AND t.name = 'Claims Department' AND r.source_entity_id = (SELECT id FROM cp);

-- 4. Someone sets criticality 9: breaks the 1 to 5 rule, saved anyway (shows as an error)
SELECT pg_sleep(1.1), set_config('eax.actor', 'sipho.n', false);
UPDATE core.attribute_values av SET value_number = 9
  FROM core.attribute_types at
 WHERE at.id = av.attribute_type_id AND at.code = 'Criticality' AND av.entity_id = (SELECT id FROM cp);

-- 5. Pieter puts the link back (so the phase 1 checks still find five relationships)
SELECT pg_sleep(1.1), set_config('eax.actor', 'pieter.v', false);
UPDATE core.relationships r SET is_deleted = false
  FROM core.entities t
 WHERE t.id = r.target_entity_id AND t.name = 'Claims Department' AND r.source_entity_id = (SELECT id FROM cp);

SELECT 'sample history added: open Claims Platform > History' AS result;
