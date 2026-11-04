-- The other side of the lock: the installer's login may change a locked model.
--   psql -U eax_migrator -d eaexplorer -v ON_ERROR_STOP=1 -f tests/sql/phase2_installer_check.sql
-- Rolled back: nothing is kept.
BEGIN;
UPDATE core.models SET description = description || ' (installer check)' WHERE name = 'Insurance reference model';
UPDATE core.entities SET description = description
 WHERE model_id = (SELECT id FROM core.models WHERE name = 'Insurance reference model');
SELECT 'installer check passed' AS result;
ROLLBACK;
