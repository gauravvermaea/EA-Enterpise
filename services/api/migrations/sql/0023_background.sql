-- =====================================================================================
-- 0023_background: build phase 13.0.2 (version 0.14.1), every slow button is a background task (D273)
--   * core.tasks: link (the screen that asked, opened from the task drawer and the notification), progress (0 to
--     100, or empty while unknown) and what it is doing now
--   * core.task_files: role input (a file uploaded with the request, read by the job) or result (the file the task
--     made, kept 24 hours and then removed by the minute job)
--   * notifications: the category task (a background task of yours finished), shown on the Background tasks tab
-- Rows only: no logic in the database (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.14.1', '0023_background', 'Phase 13.0.2: slow actions as background tasks, the task drawer, task notifications');

ALTER TABLE core.tasks
    ADD COLUMN link          text NOT NULL DEFAULT '',
    ADD COLUMN progress      smallint CHECK (progress BETWEEN 0 AND 100),
    ADD COLUMN progress_note text NOT NULL DEFAULT '';
CREATE INDEX tasks_requested_by_idx ON core.tasks (requested_by, requested_at DESC);

ALTER TABLE core.task_files
    ADD COLUMN role text NOT NULL DEFAULT 'result' CHECK (role IN ('input', 'result'));

ALTER TABLE core.notifications DROP CONSTRAINT notifications_category_check;
ALTER TABLE core.notifications ADD CONSTRAINT notifications_category_check
    CHECK (category IN ('commit', 'metamodel', 'request', 'model', 'system', 'task'));
