# EA Explorer

A free, open-source enterprise architecture platform you run yourself:
- **a governed metamodel**: ArchiMate 4 and the TOGAF 10 content metamodel built in, your own metamodels edited,
  versioned, reviewed and pushed down to the models that use them;
- **the repository and its pictures**: networks, domains, impact, capability and hierarchy maps, matrices, value
  stream maps and roadmaps drawn from the data itself (always current), each opening in draw.io;
- **reports and analysis**: 30 standard reports, 49 views (diagram, catalogue, heat map, matrix), gap,
  comparison and common analysis, data quality, and Apache Superset for your own;
- **TOGAF ADM projects**: 14 project templates, the TOGAF 10 library, key questions accepted by stakeholders, Business
  Model Canvases, the Architecture Repository, documents (Mayan EDMS) and libraries;
- **governance**: private changes until committed, child models merged back, reviews, approvals and sign-off, a full
  change log;
- **bring your own AI**: an MCP server with about 120 tools and 11 guided prompts that reads, analyses and builds as the
  signed-in person, previewing every change first;
- **integration and operations**: a REST API, signed webhooks, Excel and CSV loads, one `eax` command, health,
  tagged backups and restores; single sign-on through Keycloak.

Everything runs in Docker containers from one config file. **What it does today, area by area, and what is still
planned: [docs/capabilities.md](docs/capabilities.md).**

**Documentation inside EA Explorer:** everyone signed in opens **Documentation** beside their name: every document of
the version they run (this README, everything in `docs/`, the command line's help and the release notes), grouped,
searchable, downloadable and printable. The same documents are in the **Enterprise library**, folder **EA Explorer
documentation**, refreshed at every start (D550 to D552). On the command line, `eax document` shows every command.

**All the documentation, listed with what each covers: [docs/index.md](docs/index.md).** Backup and restore
commands: [below](#backup-and-restore-from-the-command-line) and in [docs/operations.md](docs/operations.md#backup-and-restore-from-the-command-line-d227).

**Status: version 1.1.0, Release 2, released 13 Nov 2026** (tag `v1.1.0` on the `release` branch; release notes:
[releases/1.1.0.md](releases/1.1.0.md); Release 1: [releases/1.0.0.md](releases/1.0.0.md)). Release 3 is being planned (the
R3 rows in [docs/build-phases.md](docs/build-phases.md)). The short list is
below; every phase in detail: [docs/build-phases.md](docs/build-phases.md). Database design:
[docs/database.md](docs/database.md). How it is built (for developers and AI agents):
[docs/architecture.md](docs/architecture.md), [AGENTS.md](AGENTS.md); the high-level technical architecture (under 10 pages):
[docs/requirements/EA_Explorer_Technical_Architecture.docx](docs/requirements/EA_Explorer_Technical_Architecture.docx). Requirements and the build plan:
[docs/requirements](docs/requirements). Decisions: [docs/decisions.md](docs/decisions.md). Open items:
[docs/todo.md](docs/todo.md).

## Build phases

The major phases; each line covers its sub-phases. **In detail (every sub-phase, version and notes):
[docs/build-phases.md](docs/build-phases.md).**

| Phase | What it is | State |
| --- | --- | --- |
| 0 | Foundations: the platform, sign-in, health, jobs, backups | closed |
| 1 | The metamodel store and the ArchiMate 4 seed | closed |
| 2 | Insurance reference model, locked models, the library | closed |
| 3 | Metamodel editing and versions; roles and permissions | accepted |
| 4 | Creating and copying models, library models and packages | closed |
| 5 | Report views and the thirty standard reports | closed |
| 6 | Data entry in forms | closed |
| 7 | Grids, search and saved views | closed |
| 8 | Commits; notifications and webhooks; views and TOGAF reports; tags, comparison and gap analysis; backups | closed |
| 9 | The change log | closed |
| 10 | Administration console; import and export sheets | closed |
| 12 | Validation and data quality; start-up in two tiers | closed |
| 13 | Architecture projects: library, wizard, repository, sign-off, content framework, bases, governance, charter, the Architecture Repository, tracking sheets, the console, eaxpy | accepted and closed (8 Nov 2026) |
| 15.2 | The enterprise library and project libraries (a separate service); skills on each user's profile | accepted and closed (9 Nov 2026) |
| 15.3 (part) | Business architecture: Business Model Canvases, the TOGAF Phase B artifacts and their views; key questions | accepted and closed (9 Nov 2026); the rest replaced by an *Other views and documents* project tab of sample templates (D358, D415; built in 0.17.0, D429, to be accepted) |
| 16.3 | Guided wizards | accepted and closed (9 Nov 2026) |
| 28, 29 | Drawn views in draw.io: ArchiMate notation, from the model's own entities, relationships added from the canvas; "view" everywhere (D354, D355) | released in 1.0.0 |
| 19, 20 | Merge a child into its parent: a wizard with three-way review and approval, then freeze or refresh the child (D359, D422 to D425) | released in 1.0.0 |
| 21 | Dedupe within a model: a wizard, committed like any change; old IDs still find the one kept (D361, D426 to D428) | released in 1.0.0 |
| 24 | KPI trends, an OData feed, a report designer opening Superset (D365) | released in 1.0.0 |
| 25 | Machine access: tokens, API keys and client certificates with API areas set by admins (D366) | released in 1.0.0 |
| 26, 27, 27.1 | MCP: OAuth remote connector, AI activity log, citations (D368); scenario planning with AI in projects (D364) | released in 1.0.0 |
| 33, 33.1 | ArchiMate exchange and conformance: dropped until the ArchiMate 4 exchange specification is published (D385, D386) | dropped |
| 34 | Published import formats (ArchiMate 4, Excel, a CSV format close to the Excel imports), delivered by file drop, upload or API; no ETL (D370) | released in 1.0.0 |
| 35, 35.1 | Usage insight, metrics, retention and housekeeping, database health (D371) | released in 1.0.0 |
| 36, 36.1 | Deployment kinds, upgrades with rollback (in place from GitHub releases), moving installations, key vault, AD groups (D372); test automation with security tests (D367) | released in 1.0.0 |
| 8.5, 36.3 | Release process, scaling out set in the web application (D373, D378); 36.2 removed (D380) | released in 1.0.0 |
| 38.1 | Surveys: designer with conditions, recipients by person, role, model or project, task list and link, anonymous, results and Excel (D375, D446 to D449) | released in 1.0.0 |
| 40 | EA capability maturity: assessments as surveys on nine elements and six levels, scores, targets, gaps, evidence and trend (D377, D450 to D453) | released in 1.0.0 |
| 37, 38 | Release candidate: in-page help and guides (D374); version 1.0 (D375) | released in 1.0.0 |
| 39 | Industry models from the owner's documents (D376) | released in 1.0.0 |
| 22, 23, 30, 31 | Closed as covered (D357, D362, D363) | closed |
| R2 | Release 2, first: a usable UI with a simple nine-area menu (R2.0); then the full self-test working end to end and every bug it finds fixed (R2.0.1); then the self-test and test bench in their own container, stable start-up, on-screen help showing, layout switching, stencil and explorer on standard views in draw.io, remote instances, farms of installations | planned |

## Quick start (laptop)

You need Docker Desktop (Windows or macOS) or Docker Engine with Compose v2 (Linux), 4 CPU cores,
16 GB of memory and about 15 GB of disk for the images.

Windows (PowerShell or Command Prompt, in this folder):

```powershell
.\eax clean-run      # FIRST TIME (and after pulling a new version): builds everything from scratch
.\eax clean-restart  # TESTING a new version: down, then clean-run (empty databases, images rebuilt)
.\eax trust          # OPTIONAL, once after the first clean-run: trust the local certificate (no browser warnings)
.\eax run            # NEXT TIME ONWARDS: starts it again, keeping your data
.\eax run --wait-all # the same, but waits until everything (reports, documents, draw.io, sample data) is up
.\eax help           # every command by group; .\eax help stop shows one in full; .\eax help --all everything
.\eax console        # SOMETHING WRONG? a numbered menu to get it back up (no technical knowledge needed)
```

Every command and the console are described in detail in [docs/command-line-and-console.md](docs/command-line-and-console.md).
The same commands also run as one Python program on every system: `.\eaxpy <command>` (Windows) or `./eaxpy.sh <command>`
(it fetches uv into `work/tools` the first time; phase 13.9).

**Starting takes a minute or two** (D255): `up`, `run` and the `clean-*` commands start the core first (sign-in, the
API, the screens) and say *"EA Explorer is ready: you can sign in"*; Reports, Documents, draw.io and the sample data
follow in the background, and the header shows each in red, amber or green (down, starting, up). Add **`--wait-all`** to
any of them to wait until everything is up instead. See [How EA Explorer starts](docs/operations.md#how-ea-explorer-starts-phase-121-d255).

- **`clean-run`** is for the first time, and again whenever you take a new version from GitHub. It
  starts from scratch in one step: it deletes the databases, documents and the work folder (without
  asking), creates `work\eaexplorer.env` from the laptop template, then builds and starts everything
  and prints the addresses and logins. Use `.\eax clean-run server` on a server (then replace every
  change-me value in the config file).
- **`clean-restart`** is for testing a new version while EA Explorer is running: it brings the
  containers down, then does a `clean-run` (empty databases, our images rebuilt). The trusted
  certificate is kept.
- **`run`** is for every time after that: it starts the containers again and keeps your models,
  documents and settings. (It is the same as `.\eax up`.)
- **`trust`** is optional, run once after the first `clean-run`. EA Explorer serves everything over https with
  its own local certificate; `trust` adds that certificate to your Windows trusted certificates (Windows
  asks you to confirm: choose Yes), so Edge and Chrome open `https://localhost` without a warning.
  `clean-run` keeps the certificate, so you do not need to run `trust` again. If you do not run it,
  everything still works as before: accept the browser's warning once for localhost, reports.localhost
  and docs.localhost. See
  [Certificate and https](#certificate-and-https) below.
- `.\eax stop` stops everything and keeps your data (`.\eax down` is the same; `.\eax restart` stops and starts again); `.\eax logins` prints the user names and passwords again.

`.\eax` is a small launcher (`eax.cmd`) that runs `eax.ps1` with the PowerShell execution policy
bypassed for that run only, because the script is not signed. The long form is:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\eax.ps1 run
```

Linux or macOS:

```bash
./eax.sh clean-run    # first time (and after pulling a new version)
./eax.sh trust        # optional, once: macOS adds the certificate to your keychain; Linux prints the sudo commands
./eax.sh run          # next time onwards
./eax.sh help
```

The step-by-step form of `clean-run` is `init laptop` (creates the config file) then `up` (builds and
starts); `cleanup --all` empties everything first.

### Setting up the environment: laptop, server, cloud

Every installation has one config file, `work\eaexplorer.env`, made from a template for its kind of environment.
**`clean-run` and `clean-restart` make it themselves** (they delete the old one first), for a **laptop** unless you
name another kind. To make it on its own, without starting anything, use `init`; it never overwrites a config file
that is there (run `cleanup` first to start again).

**Laptop** (the default; every password is the known laptop one, `eax logins` prints them):

```powershell
.\eax init laptop          # the config file only (the same as .\eax init)
.\eax up                   # build and start
# or both in one step, from scratch:
.\eax clean-run            # = cleanup --all, init laptop, up
```

**Server** (this machine is the server; Linux shown, `.\eax` on Windows Server works the same):

```bash
./eax.sh init server        # the server template; asks for the backups folder (a mounted share or volume, EAX_BACKUP_DIR)
nano work/eaexplorer.env    # replace EVERY change-me value: EAX_HOSTNAME, the passwords, the certificate settings
./eax.sh check              # Docker, the config file and the compose files are valid; starts nothing
./eax.sh up                 # build and start
# or from scratch in one step (then edit the config file and run ./eax.sh restart):
./eax.sh clean-run server
./eax.sh clean-restart server   # the same while it is running
```

**Another server over SSH, or a new machine in AWS, Azure or DigitalOcean** (the guided deployment: it makes the config
file with every password generated, installs Docker when missing, starts EA Explorer and checks it):

```powershell
.\eax deploy --plan                           # shows every step and command, runs nothing
.\eax deploy                                  # asks: console or web page, then where
.\eax deploy --kind server                    # a server you reach over SSH
.\eax deploy --kind aws                       # also azure, digitalocean (a new machine from your credentials)
```

The same from the screens: the site picker (top left) › **Deploy EA Explorer**; the new site is added to **Sites**
when it is ready. On a machine without EA Explorer yet, `eax-deploy.cmd` (Windows) or `eax-deploy.sh` (Linux, macOS)
downloads the version you choose and then runs `eax deploy`. Every step in detail: [docs/deployment.md](docs/deployment.md).

**A container platform** (Docker Swarm or another orchestrator, no Docker socket and no local disk): start from the
server template, then set `EAX_PLATFORM=managed` (self-tests go to the always-on test runner service) and
`EAX_FILE_STORE=database` (the self-test's files and exports kept in the database), and give the passwords as Docker
secrets if you like (D635):

```bash
./eax.sh init server
# in work/eaexplorer.env: EAX_PLATFORM=managed, EAX_FILE_STORE=database, EAX_BACKUP_DIR=<a mounted volume>
```

**Changing the kind later** (a laptop config to a server one): `init` will not overwrite, so keep a copy, then
`.\eax cleanup` (deletes the work folder, keeps the databases unless `--all`) and `.\eax init server`.

This section is also in the app: Documentation › Setting up an environment (docs/setting-up.md), and the Start page links to it.

Everything local lives in the **work** folder, which is in `.gitignore` and never committed: the config
file (`work/eaexplorer.env`), the logs (`work/logs`) and laptop data (`work/data`: backups, imports,
exports, certificate) and `work/backups` (every backup and restore log). `.\eax cleanup` empties it,
**backups and restore logs included** (copy `work/backups` elsewhere first to keep them); `.\eax cleanup --all`
also deletes the Docker volumes so the databases start empty.

### Check your installation

Once it is up, test it: **System admin › Self-test** › Smoke test › Start (it prepares what it needs); or
`.\eax test --smoke` (`./eax.sh test --smoke`); or from another machine `.\eax testbench --target https://<host>
--i-own-this --smoke`. Results: Self-test › History, the HTML or Excel report, `testbench/reports/`, and the exit code.
The full steps, what the coverage summary and the outcomes mean, and how to clean up:
[Check your installation](docs/deployment.md#check-your-installation).

### Backup and restore from the command line

They work when the screens cannot (Linux and macOS: `./eax.sh`):

| Command | What it does |
| --- | --- |
| `.\eax backup [tag]` | An infrastructure backup now (databases, files, certificate, config) |
| `.\eax backups [words]` | Lists every backup, infrastructure (numbered) and application; words search tags, names and makers |
| `.\eax restore` | Choose an infrastructure backup from the list, what to restore (full, app, app+data, db, files), type RESTORE; every step is shown and logged |
| `.\eax restore <name\|tag\|latest> --what full --yes` | The same without questions; a tag means the newest backup with it, `latest` the newest |
| `.\eax restores` / `.\eax restore-log <id>` | Every restore with its status / one restore's whole log |
| `.\eax delete-backup <name>` / `.\eax delete-restore <id>` | Deletes a backup / forgets a finished restore and its log |
| `.\eax app-backup [tag]` | Backs up every model now |
| `.\eax restore-app [run\|tag\|latest]` | Restores every model of an application backup, each over itself |
| `.\eax stop-backup` | Stops the backups running (the partial backup is deleted) |
| `.\eax maintenance on\|off` | Shows the maintenance page to everyone (restores and upgrades do this themselves) |
| `.\eax restore-model` | Choose an application backup and a model, then restore it as a new model or over itself |

A restore changes nothing live until everything has been restored cleanly, puts things back if it fails, and can be
run again (see [operations.md](docs/operations.md#restore)).

**When something goes wrong:** every command writes its full output to `work/logs/eax-<date-time>-<command>.log`,
and a failed Docker step adds a diagnostics report (versions, container states, each container's last
300 log lines, the configuration with passwords masked) to that log. `.\eax debug` starts everything
and keeps recording all container logs to `work/logs/containers-<date-time>.log` until Ctrl+C;
`.\eax diag` writes a diagnostics report at any time. Send the log file rather than screenshots.

The first start takes 5 to 15 minutes (image downloads, Superset and Mayan set themselves up). Then open
**https://localhost/**. On a laptop EA Explorer makes its own local certificate; run `.\eax trust` once
(`./eax.sh trust` on macOS) so the browser trusts it for localhost, reports.localhost and
docs.localhost (Windows asks you to confirm). `clean-run` keeps that certificate, so you trust it only
once. Everything goes through nginx on https; on a laptop the API (`http://localhost/api/docs`) and the
MCP server (`http://localhost/mcp`) also answer on plain http, from this computer only. Sign in as
`eaadmin`.

**Development logins (laptop only).** Every password on a laptop is `P^55w0rd1234&`. `init`, `up` and
`url` print the full list, and `.\eax logins` (or `./eax.sh logins`) prints it again:

| Account | User | Password |
| --- | --- | --- |
| EA Explorer (Keycloak realm; Superset and Mayan by SSO) | `eaadmin` | `P^55w0rd1234&` |
| Keycloak administrator (`/auth/admin/`) | `kcadmin` | `P^55w0rd1234&` |
| Superset break-glass (only with `EAX_SUPERSET_AUTH=db`) | `admin` | `P^55w0rd1234&` |
| Mayan EDMS administrator | `admin` | `P^55w0rd1234&` |
| PostgreSQL | `postgres`, `eax_app`, `eax_report`, `keycloak`, `superset`, `mayan` | `P^55w0rd1234&` |
| Mayan broker (Valkey) | (password only) | `P^55w0rd1234&` |

The helper never generates passwords. On a server, `init server` copies a template full of
`change-me` values; replace them yourself. The setup step refuses to start a server that still has a
`change-me` value or the development password.

Step-by-step checks for the phase 0 demo are in [docs/phase-0.md](docs/phase-0.md).

## How we test EA Explorer

Four layers, all in this repository ([docs/testing.md](docs/testing.md) has the full table of what each covers, how to
run it, who runs it and where the results go):

- **The code's own tests**: pytest for the API (`cd services/api && pytest -q`), the draw.io plugin's Playwright tests,
  and tests that every screen has on-screen help and every command the same help in every form of eax.
- **The self-test, inside a running installation** (System admin › Self-test, `eax test`): smoke or detailed tests of
  the API (every endpoint as every role, allowed and refused, and writes), every page and real journeys in a browser,
  read-only database checks and security scans, in test data of its own that you remove when you choose.
- **The test bench, from outside** (`eax testbench`, [docs/testbench.md](docs/testbench.md)): the same tests from
  another machine against any address you own, in Chromium, Firefox, WebKit and Edge, plus install, upgrade and load
  tests, with HTML, JSON and JUnit reports. Its test data (Excel and CSV deliveries, a metamodel workbook, documents,
  a survey, a drawn view, expected results) is in `testbench/data`, shared with the self-test.
- **CI** (`ci/github-actions-ci.yml`): the code's tests and the test bench's API and UI suites on every change; nightly
  a clean install, an upgrade from the previous release, every browser and a short load test.

## Certificate and https

Everything goes through one entry point, nginx, on **https**: the screens, the API with Swagger
(`/api/docs`), Keycloak (`/auth`), draw.io, the MCP server (`/mcp`), Superset (`reports.localhost`) and
Mayan (`docs.localhost`). No other port is published.

On a laptop the first start makes a small **local certificate authority** and signs the site
certificate with it (both in `work\data\tls`). The authority may vouch only for `localhost` and your
`EAX_HOSTNAME`, and its private key is thrown away once the certificate is signed, so trusting it cannot
be used to fake any other website.

| Command | What it does |
| --- | --- |
| `.\eax trust` | Optional. Adds `work\data\tls\ca.crt` to your Windows trusted root certificates (removing older EA Explorer ones). Run once after the first start. |
| `.\eax trust --remove` | Takes EA Explorer's certificates out of your trusted certificates again. |
| `.\eax cleanup --certificate` | Also deletes the certificate (normally `cleanup` and `clean-run` keep it). After the next start, run `trust` again. |
| `./eax.sh trust` | macOS: adds it to your login keychain (asks for your password). Linux: prints the `sudo` commands to run. |

**Not trusting it is fine.** Without `trust` everything works as before: the browser shows a
certificate warning the first time you open `https://localhost`, `https://reports.localhost` and
`https://docs.localhost`; choose *Advanced* and continue, once per name. Laptops send no HSTS header
(`EAX_HSTS` is empty), so the browser always lets you continue; MCP clients can use `http://localhost/mcp`.

A new certificate is made only when there is none, when `EAX_HOSTNAME` changes, or 30 days before it
runs out (after about two years); then run `.\eax trust` again. `.\eax up` reminds you when the
current certificate is not trusted yet.

- **Firefox** keeps its own list: set `security.enterprise_roots.enabled` to `true` in `about:config`,
  or import `work\data\tls\ca.crt` under Settings > Certificates > Authorities.
- **MCP clients** that run on Node (Claude Code, `mcp-remote` for Claude Desktop) do not read the
  Windows certificate store. Either use `http://localhost/mcp`, or tell Node about the certificate and
  open a new window:
  `setx NODE_EXTRA_CA_CERTS "C:\path\to\this\folder\work\data\tls\ca.crt"`
- **Plain http on a laptop**: the API (`http://localhost/api/docs`) and the MCP server
  (`http://localhost/mcp`) also answer on http, from this computer only (`EAX_HTTP_BIND=127.0.0.1`,
  `EAX_HTTP_API_MCP=true`). Every other http address goes to https.
- **On a server** put your organisation's certificate (`tls.crt` with its chain, and `tls.key`) in
  `EAX_TLS_DIR`; EA Explorer never replaces a certificate it did not make, plain http only
  redirects to https, and HSTS is on (`EAX_HSTS=max-age=31536000`).

## What runs

| Container | Provided by | What it does |
| --- | --- | --- |
| proxy | nginx (as is) | The only published ports (443, and 80 for redirects and, on a laptop, plain-http API and MCP); routes /, /api, /mcp, /auth, /drawio and the reports and docs sub-domains |
| web | ours | Start page with a tile for every service; heartbeat screen; Keycloak sign-in |
| api | ours | Flask API (heartbeat, Swagger at /api/docs) and the background job runner, in one container |
| setup | ours, runs once per start | Checks the config file, creates the local certificate authority and certificate when needed, renders the Keycloak realm and the Superset sample |
| backup | ours | Scheduled dumps of all four databases and Mayan's files; restore |
| db | PostgreSQL 17 | Databases eaexplorer (ours), keycloak, superset, mayan |
| dms-broker | Valkey | Task queue and locks for Mayan EDMS only; our code and Superset keep their state in PostgreSQL |
| keycloak | Keycloak | Sign-in, users and roles for every screen |
| reports, reports-init | Apache Superset (plus drivers) | Dashboards; sample dashboard on the rpt.v_heartbeat view |
| dms | Mayan EDMS | Documents |
| drawio | draw.io | Diagram editor |

## Repository layout

```
docker-compose.yml          the base stack
eax.ps1 / eax.sh            helper commands (init, up, status, logs, down, backup, restore)
deploy/
  templates/                one config template per deployment kind (laptop, server)
  compose/                  compose overrides per deployment kind
  proxy/                    nginx configuration
  postgres/initdb/          creates the four databases and logins on first start
  keycloak/                 realm template (roles, clients, first user)
  superset/                 Superset image, settings and init script
services/
  api/                      Flask API, migrations, setup, job runner, tests
  web/                      React start page and heartbeat screen
  backup/                   backup and restore scripts
testbench/                  the test bench: the self-test's tests run from outside (eax testbench)
  data/                     the test data, shared with the self-test (python -m testbench.data build)
  load/                     the k6 load test; thresholds.json its pass marks
docs/                       phase guides, operations, decisions; requirements and build plan
```

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first: an issue before a pull request, every
commit signed off (Developer Certificate of Origin), contributions under AGPL-3.0, and the rules every change keeps.
Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md); report security problems privately
([SECURITY.md](SECURITY.md)).

## Licence

AGPL-3.0 (see [LICENSE](LICENSE)). The open-source products it runs keep their own licences
([docs/licences.md](docs/licences.md)).
