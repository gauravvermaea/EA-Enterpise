-- =====================================================================================
-- 0069_api_cases: the API test harness's saved cases (R3.16; owner, 13 Nov 2026: "test API in a test harness to test an
-- api from selection")
--   A saved call with the answer expected: its method and path (with {model}, {project} ... filled from the test data
--   it runs in), query, body, the role it is called as, the status and fields expected. Beside the self-test's results,
--   in the tests schema. A table and its constraints only; no version change; no logic (D248).
-- =====================================================================================

CREATE TABLE IF NOT EXISTS tests.api_cases (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name           text NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 200),
    method         text NOT NULL CHECK (method IN ('get', 'post', 'put', 'patch', 'delete')),
    path           text NOT NULL CHECK (path LIKE '/api/%' AND length(path) <= 500),
    query          jsonb NOT NULL DEFAULT '{}'::jsonb,
    body           jsonb,
    as_role        text NOT NULL DEFAULT 'super-admin' CHECK (length(as_role) <= 40),
    expect_status  integer CHECK (expect_status BETWEEN 100 AND 599),
    expect_fields  jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by     text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE tests.api_cases IS 'The API test harness''s saved cases: a call and the answer expected (R3.16)';
