# EA Explorer

A free, open-source enterprise architecture repository:
a governed metamodel, an architecture repository, diagrams (draw.io), reports (Apache Superset),
documents (Mayan EDMS), sign-in through Keycloak, and an MCP server so you can connect your own
language model. Everything runs in Docker containers from one config file.

**All the documentation, listed with what each covers: [docs/index.md](docs/index.md).** Backup and restore
commands: [below](#backup-and-restore-from-the-command-line) and in [docs/operations.md](docs/operations.md#backup-and-restore-from-the-command-line-d227).

**Status: phase 13, architecture projects with the project library, the wizard and the repository in Documents (version 0.14.0), and phase 12.1, the start-up in two tiers (0.13.1), are built and waiting for the owner's test; every phase before them is accepted and closed, the last being phase 12, validation and data quality (0.13.0, 6 Nov 2026).** The platform runs end to end; the
repository database holds the ArchiMate 4 template, a locked insurance reference model and a sample
model; model pages show entities, relationships, graphs and history; a project model's metamodel can be
changed from the screens, every change publishing a new metamodel version; a failing-checks screen;
model locks; roles given in Keycloak and enforced by the API and the database, with test users per role on laptops; creating models (child or independent), library models, packages (zip and Excel) with an upload wizard, moving to another framework and metamodel drafts by AI; report views and the thirty standard reports as Superset dashboards; data entry in forms and a data entry page; an **MCP server** for your own language model ([docs/mcp.md](docs/mcp.md)). Phase notes are listed under [Build phases](#build-phases) below. Database design:
[docs/database.md](docs/database.md). How it is built (for developers and AI agents):
[docs/architecture.md](docs/architecture.md), [AGENTS.md](AGENTS.md); the high-level technical architecture (under 10 pages):
[docs/requirements/EA_Explorer_Technical_Architecture.docx](docs/requirements/EA_Explorer_Technical_Architecture.docx). Requirements and the build plan:
[docs/requirements](docs/requirements). Decisions: [docs/decisions.md](docs/decisions.md). Open items:
[docs/todo.md](docs/todo.md).

## Build phases

Each phase has its own notes: what it delivers, a demo, checks, how to upgrade and what is not in it.

| Phase | Name | Version | State | Notes |
| --- | --- | --- | --- | --- |
| 0 | Foundations: the platform, sign-in, health, jobs, backups | 0.0.x | closed | [phase-0.md](docs/phase-0.md) |
| 1 | Metamodel store and the ArchiMate 4 seed (read only) | 0.1.0 | closed | [phase-1.md](docs/phase-1.md) |
| 2 | Insurance reference model, locked models, library page and versions | 0.2.1 | closed | [phase-2.md](docs/phase-2.md) |
| 3 | Metamodel editing, metamodel versions and history, failing checks, model locks | 0.3.0 | accepted | [phase-3.md](docs/phase-3.md) |
| 3.1 | Roles and permissions | 0.3.1 | accepted | [phase-3.1.md](docs/phase-3.1.md) |
| 4 | Creating and copying models, library models and packages | 0.4.0 | accepted and closed | [phase-4.md](docs/phase-4.md) |
| 5 | Report views and the thirty standard reports | 0.5.0 | accepted and closed; each report checked in phase 36.1 | [phase-5.md](docs/phase-5.md) |
| 6 | Data entry in forms | 0.6.0 | accepted and closed | [phase-6.md](docs/phase-6.md) |
| 7 | Grids, search and saved views | 0.7.0 | accepted and closed | [phase-7.md](docs/phase-7.md) |
| 8.2 | Reports and views: viewpoints VP-01 to VP-25, TOGAF catalogues and matrices, dependency reports, audience dashboards, value stream map, roadmap (pulled ahead of 8) | 0.8.2 | accepted and closed; each report checked in phase 36.1 | [phase-8.2.md](docs/phase-8.2.md) |
| 8 | Commits of content (private until committed), Committer and History Viewer roles, conflicts at commit, roll back, draft model rejection, merging a model into a model, live updates | 0.8.3 | accepted and closed | [phase-8.md](docs/phase-8.md) |
| 8.3 | Model tags (frozen snapshots, a page per tag, make a tag the latest), Compare and Gap analyses as top-menu screens (any models and their tags; gaps stored in a chosen model), a filter screen, shared profiles and side-by-side details, TOGAF gap analyses with Gap entities (tagged by result), two gap results compared, gap reports GR-01 to GR-05 | 0.8.4 | accepted and closed | [phase-8.3.md](docs/phase-8.3.md) |
| 9 | The change log: one row per action, in its own database (EAX_CHANGELOG_DB_URL), everyone their own changes, Model Admins their models, Super Admins all; export and delete for Super Admins | 0.9.0 | accepted and closed | [phase-9.md](docs/phase-9.md) |
| 10 | Administration console (application and system settings applied at once, start-up settings shown, restart through the operations helper, health, licences), installation-wide formats, model Hierarchy tab, VP-26 Gap, report guides | 0.10.0 | accepted and closed | [phase-10.md](docs/phase-10.md) |
| 10.1 | Import and export sheets: choose types, Excel (.xlsx, .xlsm) or CSV set built on the fly with data, drop-downs and provisional IDs; upload with a preview into your uncommitted changes; column mappings, undo a load | 0.10.1 | accepted and closed | [phase-10.1.md](docs/phase-10.1.md) |
| 8.1 | Notifications (bell, page, home tile; action ones resolved once with a note), requests between people like tickets, installation-wide signed webhooks (never email), metamodel versions pushed down the hierarchy forced or offered, change documents | 0.11.0 | accepted and closed | [phase-8.1.md](docs/phase-8.1.md) |
| 8.4 | Backups (pulled ahead, D216): tagged infrastructure backups (every database, files, certificate, config, release and image versions; nightly and on demand; pinned; restored whole or in part from the console or `eax restore`, read only while restoring) and application backups (every model as a file with an Excel workbook inside, downloadable, restorable as a new model or over itself, portable), model backups on the model page; restores run on their own with a log, a Restores tab and a maintenance page, idempotent, everyone notified, models locked while restored; backups searchable, stoppable and restorable whole from the console or the command line; documents and diagrams added in phase 13 | 0.12.0 | accepted and closed | [phase-8.4.md](docs/phase-8.4.md) |
| 12 | Validation and data quality (D239, D241, D242): a Quality tab on every project model (score, completeness, rules passed, fresh, orphans, seals, charts, everything drilling down to the entities with actions), rules of four kinds without SQL (errors block a commit, warnings do not), who is responsible for each entity, a stale period with one-click "still current", seals, settings and weights inherited (a Model Admin's change waits for a Super Admin), weights set in the metamodel and shown while typing, notifications as it happens and a weekly digest, the estate on Administration > Quality with the choice of which models are measured (archived never), PDF and Excel downloads with drill-downs, reports QR-01 to QR-04, MCP tools; calculated in the background and stored (only one entity checked at once), highlights and reasons on the entity page, form and grids, entity type scores, not applicable and leave out with approvals in bulk, model icons, several API and job servers (`eax servers`) | 0.13.0 | accepted and closed |  [phase-12.md](docs/phase-12.md) |
| 12.1 | Start-up in two tiers (D255): the core (sign-in, the API, the screens) first, then Reports, Documents, draw.io, backups and the sample data in the background; `--wait-all` to wait for everything; the start-up status for everyone in the header (red, amber, green: down, starting, up) and per container for admins. Pictures open in the platform's draw.io in a new tab instead of downloading a file (D256). The grid's commit is one icon on the left of a saved row (D257) | 0.13.1 | built, waiting for the owner's test | [phase-12.1.md](docs/phase-12.1.md) |
| 13 | Architecture projects (D258-D266, phases 13 and 15 merged): the project library (TOGAF 10, the sample repository and the phase-wise deliverables: 13 phases, 116 steps, 171 deliverables and artifacts, 51 folders; Super Admins only); template libraries (EA Explorer's own with a file for every item, TOGAF 10 loaded once, your own uploaded as a zip) and the setup a Super Admin finishes before the first project; its own connection string (EAX_PROJECTS_DB_URL) so it can move to its own database; an eight-step wizard (purpose, template libraries, models added, derived or created, viewpoints, principles, steps and deliverables phase by phase with not_for_use, people and sign-off); project roles (Project Admin, Lead Architect, Architects, Model Admin, Model Sub Admin, Stakeholders); the repository in Documents (Mayan cabinets, versions, check-out and check-in for editing in Office, undo check-out); the TOGAF templates loaded once by a Super Admin, never in git; Mayan's memory fixed | 0.14.0 | built, waiting for the owner's test | [phase-13.md](docs/phase-13.md) |

Next, in order (D147, D161, D179, D181, D258): **13.0.1** design session: principles, a project's execution and changing a running project (D267) · **13.1** approvals and the project dashboard · **13.2** the registers · **13.3** ADM cycles, child projects, merging back, generating artifacts and library projects (D265) · **13.4** business architecture artifacts such as the Business Model Canvas, to be discussed first (D268) · **15.1** the organisation-wide repository · **16.3** guided wizards. Backup and restore (8.4) was pulled ahead (D216); its documents and diagrams come with phase 13. Phase 8.5 and the start page clean-up towards the end.
The full plan (54 phases) is in [docs/requirements/EA_Explorer_Build_Plan.xlsx](docs/requirements/EA_Explorer_Build_Plan.xlsx).

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
.\eax help           # what every command does
```

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
- `.\eax down` stops everything; `.\eax logins` prints the user names and passwords again.

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

Everything local lives in the **work** folder, which is in `.gitignore` and never committed: the config
file (`work/eaexplorer.env`), the logs (`work/logs`) and laptop data (`work/data`: backups, imports,
exports, certificate) and `work/backups` (every backup and restore log). `.\eax cleanup` empties it,
**backups and restore logs included** (copy `work/backups` elsewhere first to keep them); `.\eax cleanup --all`
also deletes the Docker volumes so the databases start empty.

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
docs/                       phase guides, operations, decisions; requirements and build plan
```

## Licence

AGPL-3.0 (see [LICENSE](LICENSE)). The open-source products it runs keep their own licences
([docs/licences.md](docs/licences.md)).
