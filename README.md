# EA Explorer

A free, open-source enterprise architecture repository:
a governed metamodel, an architecture repository, diagrams (draw.io), reports (Apache Superset),
documents (Mayan EDMS), sign-in through Keycloak, and an MCP server so you can connect your own
language model. Everything runs in Docker containers from one config file.

**Status: build phase 3.1 (version 0.3.1): roles and permissions.** The platform runs end to end; the
repository database holds the ArchiMate 4 template, a locked insurance reference model and a sample
model; model pages show entities, relationships, graphs and history; a project model's metamodel can be
changed from the screens, every change publishing a new metamodel version; a failing-checks screen;
model locks; roles given in Keycloak and enforced by the API and the database, with test users per role on laptops; an **MCP server** for your own language model ([docs/mcp.md](docs/mcp.md)). Phase notes:
[0](docs/phase-0.md), [1](docs/phase-1.md), [2](docs/phase-2.md), [3](docs/phase-3.md), [3.1](docs/phase-3.1.md). Database design:
[docs/database.md](docs/database.md). How it is built (for developers and AI agents):
[docs/architecture.md](docs/architecture.md), [AGENTS.md](AGENTS.md). Requirements and the build plan:
[docs/requirements](docs/requirements). Decisions: [docs/decisions.md](docs/decisions.md). Open items:
[docs/todo.md](docs/todo.md).

## Quick start (laptop)

You need Docker Desktop (Windows or macOS) or Docker Engine with Compose v2 (Linux), 4 CPU cores,
16 GB of memory and about 15 GB of disk for the images.

Windows (PowerShell or Command Prompt, in this folder):

```powershell
.\eax clean-run      # FIRST TIME (and after pulling a new version): builds everything from scratch
.\eax trust          # OPTIONAL, once after the first clean-run: trust the local certificate (no browser warnings)
.\eax run            # NEXT TIME ONWARDS: starts it again, keeping your data
.\eax help           # what every command does
```

- **`clean-run`** is for the first time, and again whenever you take a new version from GitHub. It
  starts from scratch in one step: it deletes the databases, documents and the work folder (without
  asking), creates `work\eaexplorer.env` from the laptop template, then builds and starts everything
  and prints the addresses and logins. Use `.\eax clean-run server` on a server (then replace every
  change-me value in the config file).
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
exports, certificate). `.\eax cleanup` empties it; `.\eax cleanup --all` also deletes the Docker
volumes so the databases start empty.

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
