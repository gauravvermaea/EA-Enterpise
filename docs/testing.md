# Testing EA Explorer

How EA Explorer is tested, all of it: the code's own tests, the **self-test** inside a running installation, and the
**test bench** outside it. Decisions D522 to D525, D529, D575 to D582.

## Testing, simply (R2.0.1, D592, D593)

Two choices, from the screen or the command line, nothing else to pick:

| | From the screen | From the command line | What it tests |
| --- | --- | --- | --- |
| **Smoke test** | System Admin › Tools › Self-test › **Start the smoke test** | `eax test` | every role signs in, every main area answers, every page opens, the key journeys work once (a few minutes) |
| **Full test** | System Admin › Tools › Self-test › **Start the full test** | `eax test full` | every API endpoint as every role (allowed and refused), the database, security, then every page and every journey in a headless browser |
| **Delete test results** | Self-test › History › a run's Delete, or Delete all test results... (and Keep test results N days) | `eax test delete 12`, `eax test delete all`, `eax test delete --older-than 30` | each run's test data, results and screenshots, report, log and videos, for good; old runs also go by themselves after the days set (default 30) (D610) |
| **The backup checks** | Self-test › Detailed › Backups (the last part of Full) | `eax test backup` | an infrastructure and an application backup, each restored into a scratch copy and counted, then removed; nothing live is touched (D608). Until they pass, the Backups page shows the commands instead of its buttons |
| **The restore test** | the command line only | `eax test restore` (and the end of `eax test full` from the command line, asked first; `--yes` skips the question) | back up, change, restore every way (all models, one model over itself, the infrastructure backup db, app+data, files, full) and compare all the content each time, on this installation, with no time limit; the safety backup is put back if anything fails (R3.8, D659) |
| **The API harness** | Self-test › API harness | `eax test api GET /api/v1/models --as architect` | one call to any endpoint as yourself or a test role (reads anywhere, writes into test data only), its answer and a curl line; saved cases run by every self-test (R3.16, D662) |
| **Negative tests** | part of the Full test (API) | `eax test full` | every write sent bad JSON and a list instead of an object, every read an id that is not there, long names inside the test data: refused, never a server error (R3.9, D663) |
| **Code coverage** | Self-test › a run: the gauge, areas, trend and negative tests | the line at the end of `eax test` | the API's lines run against the goal of 90% (EAX_COVERAGE_GOAL); a warning under it, a failure if an area falls by more than 2 points (R3.9, R3.10, D664) |
| **Watch a run** | Self-test › a run going on › **Watch** (Stop the run there too) | `eax test watch [run] [--log]`, `eax test stop [run]` | the step now and what it checks, each check as it is recorded, each failure with its reason, the counts and the log, live (R3.2, D666) |
| **Run the failed ones again** | Self-test › History (or a run's results) › **Run the failed ones again** (tick *and the warnings* for those too) | `eax test failed` (the last finished run) or `eax test failed 12 --warnings` | only the checks that failed in that run, as the same roles, in fresh test data; the report shows each check then and now, and the earlier run is marked followed up when all pass (D605). A full run is still what counts for a release |
| **Delete the test data** | Self-test › Test data › **Delete all test data** (or choose items) | `eax test clean` | removes every run's test data for good (type DELETE); the reports stay |

Each run ends with a **functional health** (Healthy, Degraded or Not healthy, from its critical and non-critical checks), a ring chart in the report and on the page, and a summary at the end of `eax test`: counts per suite and every failure by name (D604). Each run: does not depend on the sample data or the industry packs, so it can start as soon as EA Explorer is up (D595); removes the test data earlier runs left (a run stopped by an error is closed first); starts a **test container**
of its own; makes the models, project and test accounts it needs (`self_test_<id>_<n>`); tests only inside them; writes
the report (History, and `work/tests/<run>/report.html`); and removes the container. Nothing else changes. Runs started
on the screen and from the command line are the same and show in the same History.

What only the command line does: `eax test --reset-survival --confirm <name>` (a real reset that deletes all data, to
check settings survive it) and the older detailed options (`--suite`, `--role`, `--area`, `--journey`, `--pages-only`),
kept for scripts and CI but no longer shown.

## Every kind of test

| What | What it covers | How to run it | Who runs it | Where the results go |
| --- | --- | --- | --- | --- |
| **Unit and API tests** (pytest, `services/api/tests`) | the API's code, permissions, migrations' SQL, the eax command's help in every form, the test bench's own code and data | `cd services/api && pytest -q` (lint: `ruff check .`) | developers; CI on every change | the terminal; CI's log |
| **draw.io plugin tests** (`deploy/drawio/tests`) | every message between EA Explorer and the draw.io plugin: stencil, placing, binding, lines | `node deploy/drawio/tests/tests.cjs` (Playwright); CI checks the plugin's syntax | developers | the terminal, screenshots in that folder |
| **Help catalogue and documentation tests** (`test_help_catalogue.py`, `test_documentation.py`, `test_eax_help.py`) | every page, tab, field and button has on-screen help; every document is in Documentation; the eax help is the same in all four forms | with pytest; `python3 tools/help_inventory.py --missing` lists what has no help | developers; CI | the terminal |
| **Self-test, from the browser** | the running installation from inside: smoke or detailed (API, UI, database, security), every page, journeys | System admin › Self-test | Super Admins, IT Admins | Self-test › History, the HTML and Excel report, MCP `test_results` |
| **Self-test, from the command line** | the same | `eax test`, `eax test --detailed` … (below) | admins; CI | the same, and the exit code |
| **Test bench, CI only since R2.0.1** ([testbench.md](testbench.md)) | the same checks from another machine, as people reach it, in Chromium, Firefox, WebKit and Edge | `eax testbench --target https://<host> --i-own-this` | admins, testers; CI | `testbench/reports/<time>`: report.html, report.json, junit.xml; also Self-test › History |
| **Install test** | the deploy wizard installs a working EA Explorer | `eax testbench install --answers <file> …` | CI nightly; before a release | the test bench's report |
| **Upgrade test** | an update keeps the data, moves the version and the database migration | `eax testbench upgrade --from <tag> --to <tag> …` | CI nightly (from the previous tag); before a release | the test bench's report |
| **Cross-browser** | every page and journey in each browser | `eax testbench … --browsers all` | CI nightly; testers | the test bench's report, by browser |
| **Load test** | response times (p50, p95, p99), errors and throughput under N people | `eax testbench load --users 50 --minutes 5` (k6) | CI nightly (short); before a big roll-out | the test bench's report; thresholds in `testbench/thresholds.json` |
| **Security scans** | headers and cookies, the front door, pip-audit, OWASP ZAP baseline, Trivy on the images | the self-test's security suite, or `eax testbench --suite security` | admins; CI | the reports' security section |
| **Reset-survival** | settings in `persist/` outlive a real reset (DELETES ALL DATA) | `eax test --reset-survival --confirm <name>`, or the test bench's `--reset-survival` | Super Admins, on a laptop or a test installation | Self-test page; `persist/test-results/` |

### CI: what runs when

| When | What |
| --- | --- |
| every push and pull request | API lint and tests (with the test bench's own tests), the web build, the compose files and images, the plugin's and the k6 script's syntax, the test data as built, and the test bench's **API and UI suites** against EA Explorer started on the runner |
| nightly (02:17) | the test bench: a clean **install** with the deploy wizard, **every browser**, a short **load** test, and an **upgrade** from the previous tag |
| a version tag | the release check and the GitHub release with its notes |

The rest of this page is the self-test in detail. The test bench has its own page: [testbench.md](testbench.md).

## The self-test (inside)

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

Every fixture is recorded in `tests.test_fixtures` with its run. The tests change only these; standard screens and other
models are only read. Runs can be repeated as often as you like: new ids, new fixtures. Fixtures are hidden from model
lists (tick **Show self-test runs** to see them), from quality measures and from KPIs. Usage figures and backups still
count them until they are purged.

## The test runner

Self-tests run in a container image of their own, the **test runner** (the API's code, Chromium for the browser tests
and the security scanners; about **1.5 GB**). **Nothing to build by hand** (owner, 11 Nov 2026, D584):

- **Every test prepares it first**: Start on **System admin, Self-test** and `eax test` (any suite) run
  `docker compose --profile test build testrunner` before the run. Docker's layer cache makes that a few seconds when
  the image is current; it is rebuilt when the code or the version changed (the image is tagged with the version, so an
  older version's runner is never used). The first time takes 5 to 15 minutes and needs the internet; the page and the
  console say "Preparing the test runner...", then the run starts by itself.
- **Built in the background after every start or update** (on by default: `testrunner_auto_build` in
  `persist/settings.json`; the box is under Advanced on the Self-test page), so a test right after `eax up` or
  `eax clean-restart` does not wait. It takes about 1.5 GB of disk.
- **Advanced › Rebuild the test runner** on the page (`eax test --build`) is there for the rare case it is wanted on
  its own; its steps and log show live, with Retry.

## Running a test

On **Run**, choose:

- **Smoke test**: every role signs in, every main area answers, **every page opens** (as Super Admin) and the three key
  journeys work once (model content, quality and duplicates, the project's iteration). 2 to 5 minutes.
- **Detailed tests**: tick API, UI, Database and Security. UI runs **headless on the server**, or tick
  **Watch it in this browser** to see it in a frame on this page with a step list (keep the tab open).
- **Pages only**: just the page sweep. **Journeys**: tick some to run only those (none ticked: every journey).
- **Role** and **Area** narrow either kind.

Under the options, **The same from the command line** shows the exact `eax test` command for what you picked, as you
pick it; choose how you type eax (`.\eax`, `./eax.sh`, `.\eaxpy`, `./eaxpy.sh`) and press **Copy**. The folded
**From the command line** section lists every option of `eax test` and its examples, read from the command-line help, so
it is always the same as `eax help test` (D578). Each run in **History** shows the command it equals.

### Every page (D575)

The page sweep opens every top-level page of EA Explorer on the run's own model and project, then every group, tab and
sub-tab each page shows (the navigation registry and the tab bars), and nothing of anyone else's. Each page must render
(no script error, no server error from the API, not "not found"), show a heading, and open help on F1. The report says
**pages opened N of N**. The break-glass sign-in, the heartbeat and the SQL window are skipped, with the reason.

### Journeys (D576)

Journeys click, type and save like a person, only inside the run's `self_test_<id>_n` fixtures: model content (create
an Application Component in a form, find it, its changes and history), quality and duplicates (find the seeded pair and
merge it), the project (Transition Planning, the frozen phase, back to Full cycle, the iteration history), help and
documentation (F1 and the documentation search), admin (an admins-only banner and a schedule, made and removed; the
real banner and schedules are put back afterwards), the drawn view (headless only, as draw.io's editor is on its own
origin: drop, bind, create through the pop-up, draw a line, name it with a key:value, undo, save, reopen), import (upload
testbench/data's good delivery, accept, undo), survey (make, send, answer as the run's architect, Excel) and child merge
(send self_test_<id>_2, accept as the parent's Model Admin, refresh). Each runs as every role allowed, then once as a role
that may not, who must find the button missing or disabled (D583). The smoke test runs the first three, once.

**Start** shows how long it should take and asks you to confirm. Then you see live counts, the current step and the
failures as they come, with **Stop**. Tests always start at once; there is no scheduling. A run whose test runner was restarted or removed (an `eax up` while it ran) closes itself as stopped within a few minutes, or at once on **Stop**: whoever runs a run touches `.alive` in its folder every 20 seconds, and a running run without one for 3 minutes is no longer being run (R2.64, D656).

## Results and the report

The report starts with the **coverage**: pages opened N of N, journeys, endpoints refused without a sign-in, reads
as every role, writes by area, database and security checks, each as passed out of run (D577).

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
eax test --pages-only        only the page sweep (every page, group, tab and sub-tab)
eax test --journey duplicates   one journey by part of its name (repeat for more)
eax test --status            the run going now
eax test --last              the last run's results
eax test --report [run] [--xlsx]   save the report
eax test --fixtures [run]    list fixtures
eax test --clean <run|all> [--yes]   purge fixtures (asks you to type DELETE without --yes)
eax test --build             optional: only (re)build the test runner image (every test does this first)
```

`eax test` shows progress as it goes and exits non-zero when anything failed, so CI can use it (`--ci`).

## What each suite checks

| Suite | Checks |
| --- | --- |
| API | every endpoint in the OpenAPI description as every test role and with no role: allowed where it should be, refused where not, another model's content refused; **writes** area by area inside the fixtures (content, relationships, metamodel, surveys, the run's own token, a merge request) and the same writes refused to a role without the right (D577) |
| UI | every page opens, renders, has a heading and F1 help; journeys that click, type and save, per role allowed and refused (Playwright, Chromium; or watched in your browser) |
| Database | read-only: primary keys, the history guard on and every current version in the history, values stored as their attribute's type, pick-list values on their list, relationship attribute values within their mapping, drawn views bound only to their own model's entities, persist/ JSON valid, fixtures named after their run, indexes on foreign keys (a warning) |
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

## The same tests from outside

The test bench runs these same checks (the same code, the same names and filters) from another machine, in any
browser, and adds install, upgrade and load tests: [testbench.md](testbench.md). Its data files (`testbench/data`) are
the self-test's too: the test runner reads them at `/testdata`.

While a test runs (D609, D610): normal users wait ("Environment test in progress"), admins see only the Self-test page, and the page and the command line show how many checks are left.
