-- =====================================================================================
-- 0056_personal_schema: each person's data in the personal schema (R2.53, D632; owner, 12 Nov 2026, 21:43 and 13 Nov
--   2026, 08:38-08:45): notifications with their recipients, requests with their comments, favourites, saved views and
--   skills move from core and proj to personal, with their rows; each person's settings get a table there. The
--   personal schema may live elsewhere (EAX_PERSONAL_DB_URL, D630), so no foreign key crosses into it or out of it:
--   the application removes what refers to a model when the model is purged. While the personal data service cannot be
--   reached, notifications wait in core.personal_outbox and are sent when it is back. No database is created.
-- =====================================================================================

CREATE SCHEMA IF NOT EXISTS personal;

ALTER TABLE IF EXISTS core.saved_views   DROP CONSTRAINT IF EXISTS saved_views_model_id_fkey;
ALTER TABLE IF EXISTS core.favourites    DROP CONSTRAINT IF EXISTS favourites_model_id_fkey;
ALTER TABLE IF EXISTS core.notifications DROP CONSTRAINT IF EXISTS notifications_model_id_fkey;
ALTER TABLE IF EXISTS core.webhook_deliveries DROP CONSTRAINT IF EXISTS webhook_deliveries_notification_id_fkey;

ALTER TABLE IF EXISTS core.notifications           SET SCHEMA personal;
ALTER TABLE IF EXISTS core.notification_recipients SET SCHEMA personal;
ALTER TABLE IF EXISTS core.requests                SET SCHEMA personal;
ALTER TABLE IF EXISTS core.request_comments        SET SCHEMA personal;
ALTER TABLE IF EXISTS core.favourites              SET SCHEMA personal;
ALTER TABLE IF EXISTS core.saved_views             SET SCHEMA personal;
ALTER TABLE IF EXISTS proj.user_skills             SET SCHEMA personal;

CREATE INDEX IF NOT EXISTS favourites_model  ON personal.favourites (model_id) WHERE model_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS saved_views_model ON personal.saved_views (model_id) WHERE model_id IS NOT NULL;

-- each person's own settings (last tabs, last model and project, menu choices, notification settings ...), by key
CREATE TABLE IF NOT EXISTS personal.settings (
    username    text        NOT NULL CHECK (username = lower(username) AND username <> ''),
    key         text        NOT NULL CHECK (key ~ '^[a-z][a-z0-9_.-]{0,79}$'),
    value       jsonb       NOT NULL DEFAULT 'null'::jsonb,
    modified_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (username, key)
);
COMMENT ON TABLE personal.settings IS 'R2.53: each person''s own settings, by key';

-- what waits for the personal data service while it cannot be reached (the repository's side, never moved)
CREATE TABLE IF NOT EXISTS core.personal_outbox (
    id         bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind       text        NOT NULL CHECK (kind IN ('notification')),
    payload    jsonb       NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    tries      integer     NOT NULL DEFAULT 0,
    last_error text        NOT NULL DEFAULT ''
);
COMMENT ON TABLE core.personal_outbox IS 'R2.53: notifications made while the personal data service could not be reached';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_app') THEN
        GRANT USAGE ON SCHEMA personal TO eax_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA personal TO eax_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.personal_outbox TO eax_app;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT USAGE ON SCHEMA personal TO eax_migrator;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA personal TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA personal TO eax_migrator;
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.personal_outbox TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
END;
$$;
