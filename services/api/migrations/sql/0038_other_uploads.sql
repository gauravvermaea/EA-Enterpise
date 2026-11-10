-- =====================================================================================
-- 0038_other_uploads: version 0.17.0, a project's own uploads on the Other views and documents tab (D461; amends D415,
-- D429). They are ordinary project documents (proj.documents, files in Documents), kept in the folder
-- "00_Project/Other documents" with origin 'other': not deliverables, never signed off, not in the repository table.
--   * file_size: the current file's size in bytes, shown in the list (NULL for documents made before 0.17.0)
-- Rows only: who may upload, replace and delete is in eax/other_uploads.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.17.0', '0038_other_uploads', 'A project''s own uploads on Other views and documents')
ON CONFLICT (version) DO NOTHING;   -- several 0.17.0 migrations (batch 1): the first one writes the version

ALTER TABLE proj.documents ADD COLUMN IF NOT EXISTS file_size bigint;
CREATE INDEX IF NOT EXISTS documents_other ON proj.documents (project_id) WHERE origin = 'other';
