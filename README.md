# EA Explorer

A free, open-source enterprise architecture repository in the class of Orbus iServer and SAP LeanIX:
a governed metamodel, an architecture repository, diagrams (draw.io), reports (Apache Superset),
documents (Mayan EDMS), sign-in through Keycloak, and an MCP server so you can connect your own
language model. Everything runs in Docker containers from one config file.

**Status: build phase 1 (metamodel, read only).** The platform runs end to end (phase 0) and the
repository database is in place: the ArchiMate 4 starter metamodel, a sample model, the
`eax.get_entity` functions, read-only model pages (entities, relationships, metamodel) and an
**MCP server** for your own language model ([docs/mcp.md](docs/mcp.md)). See [docs/phase-1.md](docs/phase-1.md)
and the database design in [docs/database.md](docs/database.md); the requirements and the 40-phase
build plan are in [docs/requirements](docs/requirements).

## Quick start (laptop)

You need Docker Desktop (Windows or macOS) or Docker Engine with Compose v2 (Linux), 4 CPU cores,
16 GB of memory and about 15 GB of disk for the images.

Windows (PowerShell or Command Prompt, in this folder):

```powershell
.\eax init laptop     # creates the work folder and work\eaexplorer.env from the laptop template
.\eax up              # builds our images, pulls the others, starts everything
.\eax help            # what every command does
```

`.\eax` is a small launcher (`eax.cmd`) that runs `eax.ps1` with the PowerShell execution policy
bypassed for that run only, because the script is not signed. The long form is:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\eax.ps1 up
```

Linux or macOS:

```bash
./eax.sh init laptop
./eax.sh up
./eax.sh help
```

Everything local lives in the **work** folder, which is in `.gitignore` and never committed: the config
file (`work/eaexplorer.env`), the logs (`work/logs`) and laptop data (`work/data`: backups, imports,
exports, certificate). `.\eax cleanup` empties it; `.\eax cleanup --all` also deletes the Docker
volumes so the databases start empty.

**When something goes wrong:** every command writes its full output to `work/logs/eax-<date-time>-<command>.log`,
and a failed Docker step adds a diagnostics report (versions, container states, each container's last
300 log lines, the configuration with passwords masked) to that log. `.\eax debug` starts everything
and keeps recording all container logs to `work/logs/containers-<date-time>.log` until Ctrl+C;
`.\eax diag` writes a diagnostics report at any time. Send the log file rather than screenshots.

The first start takes 5 to 15 minutes (image downloads, Superset and Mayan set themselves up). Then open
**https://localhost/**. Your browser warns about the self-signed certificate on a laptop; accept it
once for localhost, reports.localhost and docs.localhost. Sign in as `eaadmin`.

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

## What runs

| Container | Provided by | What it does |
| --- | --- | --- |
| proxy | nginx (as is) | The only published ports (443, 80); routes /, /api, /auth, /drawio, /mail and the reports and docs sub-domains |
| web | ours | Start page with a tile for every service; heartbeat screen; Keycloak sign-in |
| api | ours | Flask API (heartbeat, Swagger at /api/docs) and the background job runner, in one container |
| setup | ours, runs once per start | Checks the config file, creates a self-signed certificate, renders the Keycloak realm and the Superset sample |
| backup | ours | Scheduled dumps of all four databases and Mayan's files; restore |
| db | PostgreSQL 17 | Databases eaexplorer (ours), keycloak, superset, mayan |
| dms-broker | Valkey | Task queue and locks for Mayan EDMS only; our code and Superset keep their state in PostgreSQL |
| keycloak | Keycloak | Sign-in, users and roles for every screen |
| reports, reports-init | Apache Superset (plus drivers) | Dashboards; sample dashboard on the rpt.v_heartbeat view |
| dms | Mayan EDMS | Documents |
| drawio | draw.io | Diagram editor |
| mail | Mailpit (laptop only) | Catches all outgoing mail at /mail/ |

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
