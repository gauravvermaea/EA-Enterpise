# Phase 36.1: Test automation, the self-test (version 0.19.0)

Built 10 Nov 2026; to be accepted. Decisions D522 to D525 and D529 (amending D367: the self-test runs on the live
installation in fixtures of its own instead of a separate test database). How to use it: [testing.md](testing.md).

## What was built

- **Build the test runner** from the page (11 Nov 2026, D570): the button runs `eax test --build` through the Command
  centre's command container, with its steps and log live and Retry; Start without it offers Build, then run; and an
  automatic build after each start or update (persist/settings.json; off on laptops, on for servers).

- **System admin, Self-test** (Super Admins and IT Admins): Run, History and Test fixtures tabs.
- **`eax test`** in all four forms (eax.ps1, eax.sh, the Python CLI, the console), and in CI.
- **One runner** (the `testrunner` image, profile `test`, started on demand by the operations helper) and **one results
  store** (`core.test_runs`, `core.test_results`, `core.test_fixtures`, migration 0045).
- **Smoke test** and **Detailed tests** (API, UI, database, security), filtered by role and area.
- UI tests **headless on the server** (default) or **watched in this browser**.
- A **report** at the end (HTML with screenshots; Excel), from the page, `eax test --report` and MCP (`test_results`).
- **Fixtures** `self_test_<id>_1`, `_2`, `_3` and `svc-self-test-<id>-<role>` accounts, recorded per run, hidden from
  normal lists, quality measures and KPIs, and **purged only by hand** (a hard delete, typed DELETE).
- Sample data on laptops: a passed smoke run with its fixtures still there, a failed detailed run whose fixtures were
  removed (with a screenshot, a request and response, and browser names), and a run that could not finish.

## Files

| Where | What |
| --- | --- |
| services/api/eax/testing/ | store, run, fixtures, api_matrix, ui_journeys, db_checks, security, report, cli |
| services/api/Dockerfile.test | the runner image |
| services/api/eax/api/platform_tests.py | `/admin/tests...` and `/admin/scaling...` |
| services/api/eax/api/selftest_session.py | the test browser's sign-in by ticket |
| services/api/eax/mcp_tests.py | the MCP tool `test_results` |
| services/ops/testruns.py | starting the runner, the scans, `eax test`, building the runner (D570) |
| services/web/src/TestRuns.jsx | the Self-test screen and the watched run |
| services/api/eax/seed/sample_tests.py | the sample runs |

## What the watched run cannot reach

The page drives a frame on the same site. Reports (Superset), Documents (Mayan), the draw.io canvas and the library
and views services answer from their own origins or need their own sign-in, so the watched run covers the core screens
only; the API checks and the headless run cover the rest.

## What is still counted

Usage figures and backups include self-test fixtures while they exist (they are real rows). Purge them when done.

## Needs on the owner's side

Docker (the runner image, about 1.5 GB with Chromium, is built from the Self-test page, by `eax test --build`, or on first use); the internet for pip-audit's advisory
database, the Trivy database and the first pull of the ZAP and Trivy images. Without the internet those checks are
recorded as skipped.
