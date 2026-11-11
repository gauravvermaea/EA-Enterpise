# The test bench: testing EA Explorer from outside

The test bench (`testbench/`, `eax testbench`) runs **every check of the self-test from another machine**, against any
EA Explorer address you own, the way people and CI reach it: through the front door, over the network, in the browsers
you choose. Decisions D579 to D582.

## The test bench and the self-test

| | Self-test (inside) | Test bench (outside) |
| --- | --- | --- |
| Where it runs | in the installation's test runner container | on any machine that can open the address: a laptop, a CI runner |
| Started from | System admin › Self-test, `eax test` | `eax testbench`, `python -m testbench`, CI |
| What it tests | the installation, from its own network | the installation as people see it: DNS, certificate, proxy, browsers |
| The tests | services/api/eax/testing | **the same code, imported** (never copied) |
| Names and filters | `--smoke`, `--detailed`, `--suite`, `--role`, `--area`, `--journey`, `--pages-only` | the same, plus `--browsers` |
| Browsers | Chromium | Chromium, Firefox, WebKit (Safari's engine), Microsoft Edge |
| Fixtures | `self_test_<id>_n`, made by the run | the same: the target makes them for the bench's run |
| Also | the reset-survival test | install, upgrade, load, publishing results, cross-browser |
| Results | Self-test › History, report.html and Excel | testbench/reports/<time>: report.html, report.json, junit.xml; and back into Self-test › History |

A test (`tests/test_testbench.py`) fails when the inside run makes a test call the bench does not, so nothing can be
tested only inside.

## What you need

- **Python 3.12** with the packages in `testbench/requirements.txt` (Playwright, SQLAlchemy, psycopg, openpyxl, pip-audit).
  Through `eax testbench` you need nothing: eax fetches them with uv into `work/tools` (as for `eax deploy`).
- **Browsers** for the UI suite: `python -m playwright install chromium` (add `firefox webkit`). Edge: Microsoft Edge
  installed on the machine (`python -m playwright install msedge` on Windows or macOS).
- Optional: **k6** for the load test, **Docker** for the OWASP ZAP scan, **trivy** for the image scans. Each is skipped,
  with the reason, when it is not there.
- A sign-in on the target: a **Super Admin's or IT Admin's machine-access token** (System admin › Machine access), or a
  Keycloak user and password (the bench signs in through the realm's `eax-odata` client, D433).

`eax testbench setup --browsers all` says what is here and what is missing, with the command for each. The bench
installs nothing itself.

### Windows

```powershell
cd C:\EA-Explorer                      # the repository or an installation folder
.\eax testbench setup --browsers all
.\eaxpy.cmd -m pip --version           # not needed: eax testbench fetches its packages itself
.\eax testbench --target https://localhost --i-own-this --insecure --user eaadmin --password '...'
```

Without eax: `py -3.12 -m venv .venv; .\.venv\Scripts\pip install -r testbench\requirements.txt;
.\.venv\Scripts\python -m playwright install chromium; .\.venv\Scripts\python -m testbench ...`.

### Linux and macOS

```bash
./eax.sh testbench setup --browsers chromium,firefox,webkit
./eax.sh testbench --target https://ea.example.org --i-own-this --token "$EAX_TESTBENCH_TOKEN"
```

Without eax: `python3.12 -m venv .venv && .venv/bin/pip install -r testbench/requirements.txt &&
.venv/bin/python -m playwright install --with-deps chromium && .venv/bin/python -m testbench ...`.

## Targets and safety

- The bench **never runs** without `--target <address> --i-own-this`. In CI set `EAX_TESTBENCH_I_OWN_THIS=<host>`
  instead; it must be the target's host name.
- The address is the one you sign in on, without a path (`https://ea.example.org`). A laptop with its own certificate
  needs `--insecure`.
- It changes only its run's fixtures (`self_test_<id>_1`, `_2`, `_3` and the `svc-self-test-<id>-<role>` accounts),
  made by the target. Standard screens and other models are only read. Fixtures stay until you remove them.
- `--reset-survival` really **deletes every database** on the target: it needs `--confirm <installation name>` too.
- Tokens are never written to the reports. Keep credentials in a file outside the repository
  (`testbench/data/credentials.template.json` shows the shape; `testbench/data/credentials.json` is git-ignored).

## Commands

Every form of eax takes them: `.\eax testbench …` (Windows), `./eax.sh testbench …`, `.\eaxpy testbench …`,
`./eaxpy.sh testbench …`, or `python -m testbench …`. `run` is the default.

```bash
# the smoke test (the self-test's smoke, its browser part in Chromium)
eax testbench --target https://ea.example.org --i-own-this --token eaxt_...
# every suite, three browsers, every result into the target's Self-test history
eax testbench --target https://ea.example.org --i-own-this --detailed --browsers chromium,firefox,webkit --publish
# one suite, one role, one area
eax testbench --target https://ea.example.org --i-own-this --suite api --role architect --area models
# one journey; only the page sweep
eax testbench --target https://ea.example.org --i-own-this --journey duplicates
eax testbench --target https://ea.example.org --i-own-this --pages-only --browsers webkit
# the database checks directly on the database instead of through the API
eax testbench --target https://ea.example.org --i-own-this --suite db --db postgresql+psycopg://reader:...@db:5432/eaexplorer
# security without the scans
eax testbench --target https://ea.example.org --i-own-this --suite security --no-zap --no-trivy
# only what needs no sign-in (every endpoint refused without a token, the front door)
eax testbench --target https://ea.example.org --i-own-this --no-fixtures
# the target's runs going on; fixtures; clean up
eax testbench --target https://ea.example.org --i-own-this --status
eax testbench --target https://ea.example.org --i-own-this --fixtures
eax testbench --target https://ea.example.org --i-own-this --clean 12 --yes
# the last run here: its result and every failure; where its report is
eax testbench --last
eax testbench --report
# the platform's reset-survival test (DELETES ALL DATA on the target)
eax testbench --target https://localhost --i-own-this --insecure --reset-survival --confirm demo-laptop --token-after eaxt_...
# install with the deploy wizard's answers, then the smoke test
eax testbench install --target https://localhost --i-own-this --insecure --answers answers.json
# upgrade from a tag to this checkout, checking nothing is lost
eax testbench upgrade --from v0.18.0 --to v0.19.0 --answers answers.json --target https://localhost --i-own-this --insecure --user eaadmin --password ...
# load: 50 people for 5 minutes
eax testbench load --target https://ea.example.org --i-own-this --users 50 --minutes 5
# the suites and journeys; the test data
eax testbench suites
eax testbench data list
```

| Option | What |
| --- | --- |
| `--smoke` / `--detailed` | as `eax test`; `--suite`, `--journey` and `--pages-only` mean detailed |
| `--suite S` | api, ui, db, security or all (repeat for more) |
| `--role R`, `--area A` | one test role; one API area |
| `--journey J`, `--pages-only` | one browser journey by part of its name; only the page sweep |
| `--browsers B` | chromium, firefox, webkit, msedge or all |
| `--token`, `--user/--password`, `--credentials F` | how to sign in (`EAX_TESTBENCH_TOKEN`, `EAX_TESTBENCH_USER`, `EAX_TESTBENCH_PASSWORD`) |
| `--db <dsn>` | the database checks directly (default: through the target's API) |
| `--no-zap`, `--no-trivy`, `--no-fixtures` | leave those out |
| `--publish [address]` | every result into Self-test › History, of the target or of another installation (`--publish-token`) |
| `--insecure` | do not check the certificate |
| `--out F` | the report's folder (default `testbench/reports/<time>`) |

## How a run goes

1. The target's API description (`/api/openapi.json`, public) says the target answers and which version it is.
2. The bench asks the target to start a self-test run **for a browser** (`POST /api/v1/admin/tests`, watch). The target
   makes the fixtures and test accounts; the bench takes their ids, the sign-in ticket and the one-day tokens
   (`GET /api/v1/admin/testbench/runs/<run>/session`, only for the person who started that open run).
3. **Smoke**: the self-test's own smoke, every check it holds (every role signs in, every area answers, documentation,
   the Deploy page, the Command centre, banner and schedules, the project's iteration), with its browser part in each
   browser. **Detailed**: db, api (every endpoint as every role, cross-user refusals, the writes area by area and the
   same writes refused), ui (every page, group, tab and sub-tab; every journey as each role allowed and refused),
   security.
4. The results go back into the target's run, marked **external testbench**, which closes it (only the summary unless
   `--publish`).

Without a token, or when the target cannot make fixtures, only what needs none runs (anonymous refusals and the front
door), and the report says why.

## The test data

`testbench/data/` holds every file the tests use, the same files for the bench and the self-test (the test runner
mounts the folder at `/testdata`, `EAX_TEST_DATA`):

| Folder | Files |
| --- | --- |
| deliveries/ | `good.xlsx` and `good-csv.zip` (3 applications, 2 nodes, 3 relationships), `with-errors.xlsx` (no name, an unknown pick value, a delete, an unknown end), `values-win.xlsx` (changed values for a source whose values win) |
| metamodel/ | `metamodel.xlsx`: two types, three attributes, a pick list, an allowed relationship, a rule |
| uploads/ | `document.docx`, `document.pdf`, `image.png` and their `-v2` replacements |
| surveys/ | `survey.json`: every common question kind, one condition |
| views/ | `drawn-view.xml`: a draw.io view of the delivery's entities |
| entities/ | `entities.json`, `relationships.json`, `attributes.json` |
| expected/ | `expected.json`: what each file should give when loaded |
| (top) | `credentials.template.json` (no secret), `manifest.json` (every file, what it is for, who uses it, its checksum) |

The k6 scenario's data is `testbench/load/data.json`.

```bash
python -m testbench.data build     # make them again (byte for byte the same every time)
python -m testbench.data check     # are the files on disk as built? (CI runs this)
python -m testbench.data list      # what each is and who uses it
```

Change the data in `testbench/data/build.py`, build, and commit the files. A test checks every file is as built and
loads, and that every file a journey names exists.

## Reports

Each run writes `testbench/reports/<time>/`:

- **report.html**: the verdict, the totals, the **coverage summary**, the load figures, notes, then every check (failed
  first) with the request and response of an API failure and the screenshot of a UI failure inside the page;
- **report.json**: everything, for tools;
- **junit.xml**: one test case per check, for CI;
- **run.log**, **videos/** (failed journeys only), **zap.json**, **trivy-*.json**, **k6-summary.json** when they ran.

The **coverage summary**: pages opened N of N (every browser), journeys passed, endpoints refused without a sign-in,
reads as every test role, cross-user refusals, writes by area, database, security and smoke checks, the browsers, and
the load figures. Outcomes: **passed**; **warning** (works, but look: a missing header, a slow answer); **failed**;
**skipped** (could not run here, with why: a browser or tool missing, nothing to test).

The exit code is **0** when nothing failed, **1** when a check failed (or a load threshold was broken), **2** when the
command was wrong or the guard stopped it.

## Thresholds

`testbench/thresholds.json` holds the load test's marks: `p50_ms`, `p95_ms`, `p99_ms`, `error_rate` (0.01 is 1%) and
`min_rps`. The load test fails when any is broken; k6 is given the same marks. Change them there.

The load test (`testbench/load/scenarios.js`, reads only) ramps up to `--users` virtual people over a fifth of
`--minutes`, holds, and ramps down; each opens the start page, who am I, the models, the run's model and its grid, and
a search, every one to three seconds. When k6 is missing the bench says how to get it and the load test is skipped.

## CI

`ci/github-actions-ci.yml`, job **Test bench**:

- **every change**: EA Explorer started on the runner, then `--detailed --suite api --suite ui --browsers chromium`;
  `python -m testbench.data check`; the k6 script is syntax-checked with the draw.io plugin;
- **nightly** (02:17): a clean install with the deploy wizard (`ci/testbench-answers.json`) and the smoke test, every
  browser, a short load test (20 users, 2 minutes), and an upgrade from the previous tag to this commit;
- the reports are kept as the run's artifacts (`testbench-reports`).

## Troubleshooting

| What you see | What to do |
| --- | --- |
| `Run it only against an installation you own` | add `--i-own-this` (CI: `EAX_TESTBENCH_I_OWN_THIS=<host>`) |
| `CERTIFICATE_VERIFY_FAILED` | a laptop's own certificate: add `--insecure` |
| `fixtures on the target: skipped` | no token: give `--token`, `--user/--password` or `--credentials` |
| `the target could not start a self-test run (403)` | the sign-in is not a Super Admin or IT Admin |
| `(409) not waiting for a browser` | another person's or a finished run: start again |
| `browser Firefox: skipped, cannot start here` | `python -m playwright install firefox` |
| `Microsoft Edge: skipped` | install Edge (Windows, macOS) or leave msedge out |
| `load test (k6): skipped` | install k6 (the message has the link) |
| `database checks: skipped (403)` | the API's door needs a Super Admin or IT Admin; or give `--db` |
| `OWASP ZAP: skipped` / `Trivy: skipped` | Docker / trivy is not here; the self-test runs them inside |
| the platform's reset-survival result is skipped | the reset deleted the accounts: give `--token-after` with a new token |
| `data kept: … failed` after an upgrade | rows were lost: keep the report and roll back (`eax rollback`) |
| many pages "not found" | the target is older than the bench: test with the bench of the target's version |

See also [testing.md](testing.md) for every kind of testing, and the self-test in detail.
