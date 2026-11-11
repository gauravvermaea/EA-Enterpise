# Testing EA Explorer: the self-test

The self-test checks a running installation from the inside. It is for **Super Admins and IT Admins**, on
**System admin, Self-test** or with `eax test`. Decisions D522 to D525 and D529; build notes in
[phase-36.1.md](phase-36.1.md).

## How it stays safe

Each run gets an id (the first 12 characters of a guid) and makes its own **fixtures**:

| Fixture | What |
| --- | --- |
| `self_test_<id>_1` | a model from ArchiMate 4 with a few capabilities, application components and relationships |
| `self_test_<id>_2` | a child model of `_1` |
| `self_test_<id>_3` | a project that uses `_1` |
| `svc-self-test-<id>-<role>` | a test account per role, with a token valid for one day (revoked when the run ends) |

Every fixture is recorded in `core.test_fixtures` with its run. The tests change only these; standard screens and other
models are only read. Runs can be repeated as often as you like: new ids, new fixtures. Fixtures are hidden from model
lists (tick **Show self-test runs** to see them), from quality measures and from KPIs. Usage figures and backups still
count them until they are purged.

## The test runner

Self-tests run in a container image of their own, the **test runner** (the API's code, Chromium for the browser tests
and the security scanners; about **1.5 GB**). It is built once per version (D570):

- On **System admin, Self-test**, when it is missing, press **Build the test runner** (5 to 15 minutes the first time;
  it needs the internet). The page shows its steps (base image, Python packages, Chromium, scanners, the code) and the
  log as it goes, then opens the Run tab, ready. If it fails, the reason is shown with **Retry**. You can leave the
  page: the build goes on.
- Or press **Start** anyway: it offers **Build, then run**, and the run starts by itself once the runner is built.
- Or tick **Build it automatically after each start or update**: the operations helper builds it in the background
  whenever the image for the running version is missing (after start-up, after an update, and every 15 minutes). The
  setting is kept in `persist/settings.json` (`testrunner_auto_build`); off on a laptop and on for servers by default.
- From the command line: `eax test --build` builds it only; `eax test` builds it first when it is missing.

## Running a test

On **Run**, choose:

- **Smoke test**: every role signs in, every main area answers, two key journeys work once. 2 to 5 minutes.
- **Detailed tests**: tick API, UI, Database and Security. UI runs **headless on the server**, or tick
  **Watch it in this browser** to see it in a frame on this page with a step list (keep the tab open).
- **Role** and **Area** narrow either kind.

**Start** shows how long it should take and asks you to confirm. Then you see live counts, the current step and the
failures as they come, with **Stop**. Tests always start at once; there is no scheduling.

## Results and the report

**History** lists every run. **Results** shows each check with its outcome and the reason; for an API failure, *What was
asked and what came back* shows the request and the response; for a UI failure, a screenshot (and the video in the run's
files). Filter by outcome and suite. **Download report (HTML)** and **Excel** give the whole run; the report stays after
the fixtures are purged, marked "fixtures removed". Your language model can read the latest failures through MCP
(`test_results`).

## Cleaning up

Nothing is deleted automatically. On **Test fixtures**, filter by run, tick fixtures or use **All of this run** or
**All runs**, then **Delete selected** and type **DELETE**. This **cannot be undone**: the models with everything in them
(entities, relationships, values, history, tags, measurements, uncommitted changes, drawn views), the projects with
their documents, and the test accounts and credentials are removed for good. Only fixtures the self-test recorded are
touched. It runs as a task with progress and a log in **Tasks**, and the change log keeps the run and the clean-up.

## From the command line

```
eax test                     the smoke test (the default)
eax test --smoke             the same
eax test --detailed          every suite
eax test --suite api,db      chosen suites (implies --detailed)
eax test --role architect    one role;   --area models   one area
eax test --status            the run going now
eax test --last              the last run's results
eax test --report [run] [--xlsx]   save the report
eax test --fixtures [run]    list fixtures
eax test --clean <run|all> [--yes]   purge fixtures (asks you to type DELETE without --yes)
eax test --build             only build the test runner image
```

`eax test` shows progress as it goes and exits non-zero when anything failed, so CI can use it (`--ci`).

## What each suite checks

| Suite | Checks |
| --- | --- |
| API | every endpoint in the OpenAPI description as every test role and with no role: allowed where it should be, refused where not, another model's content refused |
| UI | journeys through the core screens per role (Playwright, Chromium): models, a model, entities, the project and its tasks, administration |
| Database | read-only: primary keys, the history guard on, fixtures named after their run, indexes on foreign keys (a warning) |
| Security | headers and cookies, the front door refusing unsigned calls, pip-audit, an OWASP ZAP baseline scan, Trivy on our images |

## Settings survive a reset (D561)

`eax test --reset-survival --confirm <installation name>`, or the Self-test page's opt-in tick **"Includes a full
reset: deletes all data"** (Super Admins only, the same strong confirm as clean-restart). It writes a marker schedule
(off) and a banner marker (admins only, off) named `self_test_<run>` into `persist/`, runs a **real `eax
clean-restart`** (every database and the work folder are deleted; a safety backup is taken first), waits for EA
Explorer to answer again, checks that the markers and every other file in `persist/` survived byte for byte, and
removes the markers. The result is kept in `persist/test-results/<run>.json` and `.log`, so the reset cannot delete
it, and is listed on the Self-test page. It is never part of the smoke run or the default detailed run.

The same sequence runs in the normal test suite on a temporary folder (`tests/test_persist_schedules.py`): the real
cleanup code path, then init, then reading `persist/` as the operations helper does at start-up.
