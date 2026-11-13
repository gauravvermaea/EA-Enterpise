-- =====================================================================================
-- 0062_archive_contents: what an archived model or project holds, as text, for Find with Include archived (R2.41,
--   D647; owner's answer 12 Nov 2026: "archived ones are left out of Find, search and the model and project lists unless
--   Include archived is ticked, which fetches them from the archive database"). Filled when something is archived: one
--   line per element ("Application Component: CRM"). A column only (D248). No version change.
-- =====================================================================================
ALTER TABLE archive.archive_store ADD COLUMN IF NOT EXISTS contents text NOT NULL DEFAULT '';
