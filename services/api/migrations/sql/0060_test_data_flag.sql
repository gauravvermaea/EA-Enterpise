-- Test data is marked (R2.11, D637; owner, 10 Nov 2026): the models and projects a self-test run makes carry
-- is_test_data, so the model and project lists leave them out unless asked (?test_data=1). Only a flag and an index;
-- no logic in the database (D248).
ALTER TABLE core.models ADD COLUMN IF NOT EXISTS is_test_data boolean NOT NULL DEFAULT false;
ALTER TABLE proj.projects ADD COLUMN IF NOT EXISTS is_test_data boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS models_test_data_idx ON core.models (id) WHERE is_test_data;
CREATE INDEX IF NOT EXISTS projects_test_data_idx ON proj.projects (id) WHERE is_test_data;
