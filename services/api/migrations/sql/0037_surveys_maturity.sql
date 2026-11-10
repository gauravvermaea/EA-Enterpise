-- =====================================================================================
-- 0037_surveys_maturity: version 0.17.0, surveys (phase 38.1, D375, D446 to D449) and EA capability maturity
-- (phase 40, D377, D381, D450 to D453)
--   * a survey: its questions in sections (kinds, conditions, required answers) kept as one document (spec), who it
--     was meant for (recipients_spec: people, global roles, everyone on a model or a project), draft, open or closed,
--     anonymous or not, a closing date and automatic reminders. Answers never change the model (D375)
--   * the people asked (one row each: when asked, reminded and answered) and the answers (one row a response; an
--     anonymous survey's responses carry no name and nothing joins them to the people asked)
--   * a maturity assessment is a survey of kind 'maturity' with its targets, weights and the evidence EA Explorer
--     measured (maturity), kept when it closes so the trend compares like with like
-- Child rows point at their survey by guid, so an application backup puts them back as they were (org_backup.py).
-- Rows only: the rules, conditions, scores and evidence are in eax/surveys.py and eax/maturity.py (D248).
-- =====================================================================================

INSERT INTO core.schema_versions (version, migration, description) VALUES
    ('0.17.0', '0037_surveys_maturity', 'Batch 1 (D421): surveys; EA capability maturity')
ON CONFLICT (version) DO NOTHING;   -- several 0.17.0 migrations (batch 1): the first one writes the version

CREATE TABLE core.surveys (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid             uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    kind             text NOT NULL DEFAULT 'survey' CHECK (kind IN ('survey', 'maturity')),
    title            text NOT NULL CHECK (btrim(title) <> '' AND length(title) <= 200),
    description      text NOT NULL DEFAULT '' CHECK (length(description) <= 4000),
    spec             jsonb NOT NULL DEFAULT '{"sections": []}',   -- sections and questions (eax.surveys.clean_spec)
    status           text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'open', 'closed')),
    anonymous        boolean NOT NULL DEFAULT false,
    open_link        boolean NOT NULL DEFAULT false,              -- anyone signed in who has the link may answer
    recipients_spec  jsonb NOT NULL DEFAULT '[]',                 -- [{kind: user|role|model|project, value, role?}]
    remind_every_days integer CHECK (remind_every_days IS NULL OR remind_every_days BETWEEN 1 AND 60),
    closes_at        timestamptz,
    maturity         jsonb,                                       -- kind maturity: targets, weights, evidence kept
    owner            text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    opened_at        timestamptz,
    closed_at        timestamptz,
    last_reminded_at timestamptz,
    is_deleted       boolean NOT NULL DEFAULT false
);
CREATE INDEX surveys_status_idx ON core.surveys (status, kind) WHERE NOT is_deleted;
COMMENT ON TABLE core.surveys IS 'Phase 38.1: a survey and its questions (D375); kind maturity: an EA capability maturity assessment (phase 40, D377)';

CREATE TABLE core.survey_recipients (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    survey_guid  uuid NOT NULL REFERENCES core.surveys (guid) ON DELETE CASCADE,
    username     text NOT NULL CHECK (username = lower(username)),
    via          text NOT NULL DEFAULT 'asked' CHECK (via IN ('asked', 'link')),   -- asked, or came by the link
    added_at     timestamptz NOT NULL DEFAULT now(),
    reminded_at  timestamptz,
    answered_at  timestamptz,
    UNIQUE (survey_guid, username)
);
COMMENT ON TABLE core.survey_recipients IS 'Phase 38.1: the people a survey asks, when they were reminded and when they answered (never what)';

CREATE TABLE core.survey_responses (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guid         uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    survey_guid  uuid NOT NULL REFERENCES core.surveys (guid) ON DELETE CASCADE,
    respondent   text CHECK (respondent IS NULL OR respondent = lower(respondent)),   -- empty in an anonymous survey
    answers      jsonb NOT NULL DEFAULT '{}',
    status       text NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'submitted')),
    started_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    submitted_at timestamptz,
    UNIQUE (survey_guid, respondent)
);
CREATE INDEX survey_responses_survey_idx ON core.survey_responses (survey_guid, status);
COMMENT ON TABLE core.survey_responses IS 'Phase 38.1: the answers, one row a response; no respondent in an anonymous survey';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eax_migrator') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.surveys, core.survey_recipients, core.survey_responses TO eax_migrator;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO eax_migrator;
    END IF;
END;
$$;
