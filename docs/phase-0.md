# Build phase 0: foundations

Phase 0 sets up infrastructure only. There is no repository content yet; the metamodel arrives in
phase 1. This guide is the phase 0 demo and its checklist.

## Status: accepted on 3 November 2026

Tested on Windows with Docker Desktop (8 GB):

- **Working:** the whole stack starts with `.\eax debug`; every login works, including single sign-on
  from Keycloak into Superset and Mayan EDMS (Mayan through its OpenID Connect backend); the
  heartbeat screen and the sample background job both run.
- **Deferred to later (not blocking):**
  - Remaining checklist items: Swagger, audit log, Superset sample dashboard, Mayan upload,
    backup and scratch restore, database not exposed.
  - Pin the Mayan image (`mayanedms/mayanedms:s4`, ran as 4.12.2) by digest.
  - Decide whether to drop the email settings and/or Mailpit on the laptop.

## What phase 0 delivers

**0.1 Foundations: Docker, networks, API, database and a start page**

- Docker Compose stack with two networks: `frontend` and `backend` (internal; nothing on it can be
  reached from outside).
- One config file, `work/eaexplorer.env`, created from a template per deployment kind (laptop, server).
- nginx proxy: the only published ports (443 and 80), TLS, routing.
- `api` container (Flask) connected to PostgreSQL.
- Heartbeat API: `GET /api/v1/heartbeat` returns status, version and whether the database is
  reachable. Swagger (OpenAPI) at `/api/docs`, specification at `/api/openapi.json`.
- Start page with a tile for every service; tiles for services that do not exist yet say which
  build phase delivers them.
- A heartbeat screen that calls the API every 10 seconds.
- JSON logs from the API; secrets only in `work/eaexplorer.env` (never committed). On a laptop every password is
  `P^55w0rd1234&` and the helper prints all logins (`.\eax logins`).
- CI on GitHub Actions: API lint and tests, web build, compose validation, image builds.

**0.2 Platform services and engineering spine**

- PostgreSQL with four databases and separate logins: `eaexplorer` (ours), `keycloak`, `superset`,
  `mayan`; a read-only `eax_report` login that can read only the `rpt` schema.
- Alembic migrations (first migration: schemas `library`, `core`, `staging`, `history`, `audit`,
  `jobs`, `rpt`).
- Append-only audit log (`audit.events`): updates, deletes and truncates are refused.
- Workflow skeleton: `staging.change_sets` and `staging.change_items` (used from phase 8).
- Background job runner (Procrastinate, queue in PostgreSQL) in the api container, with a sample
  job.
- Keycloak realm `eaexplorer`: the eight roles, the first administrator, clients for the web
  screens, the API, Superset and Mayan.
- Superset signed in through Keycloak, with a sample dashboard on `rpt.v_heartbeat`.
- Mayan EDMS (with Valkey as its task queue), draw.io and Mailpit running and linked from the start page.
- Backup container: scheduled dumps of all four databases and Mayan's files; restore and scratch
  restore.

## Run it

```powershell
.\eax init laptop
.\eax up               # or .\eax debug, which also records every container's log
.\eax status        # wait until api, keycloak, reports and dms are running / healthy
```

## Demo checklist

| # | Check | How | Expected |
| --- | --- | --- | --- |
| 1 | Stack is up | `.\eax status` | All services running; `setup` and `reports-init` exited with code 0 |
| 2 | Start page | Open https://localhost/ | Tiles for every service; live ones in colour |
| 3 | Heartbeat screen | Start page > Heartbeat | API **ok**, database **reachable**, schema `0001_foundation` |
| 4 | Swagger | https://localhost/api/docs | Heartbeat, me, jobs and audit calls listed; "Try it out" on heartbeat works |
| 5 | Database down is reported | `docker compose --env-file work/eaexplorer.env stop db`, refresh heartbeat, then start db again | Status **degraded**, database **not reachable**, then back to ok |
| 6 | Sign in | Start page > Sign in, user `eaadmin`, password `P^55w0rd1234&` | Signed in straight away (no password change on a laptop); your name shows top right |
| 7 | Background job | Heartbeat screen > Run a background job | Job goes todo > doing > succeeded |
| 8 | Audit | Swagger > Authorize (paste a token) or `GET /api/v1/audit` from the browser console | Events `job.requested` and `job.completed` |
| 9 | Seamless sign-in to Superset | Start page > Reports | Opens the sample dashboard **without another login** |
| 10 | Sample report | Superset dashboard "EA Explorer - phase 0 sample" | The heartbeat rows, including the job's row |
| 11 | Mayan | Start page > Documents | Mayan opens (see open item 2) |
| 12 | draw.io | Start page > Diagrams | The draw.io editor loads from this installation |
| 13 | Mail | Start page > Mail | Mailpit opens (Keycloak's "forgot password" mails land here) |
| 14 | Backup | `.\eax backup` | A dated folder in work/data/backups with four .dump files and SHA256SUMS |
| 15 | Scratch restore | `.\eax restore <folder> --scratch` | `*_restore_test` databases created; live data untouched |
| 16 | Data stays private | `docker compose --env-file work/eaexplorer.env port db 5432` | No published port for the database |

## Open items to settle in phase 0.2 (the proof-of-concept questions)

1. **draw.io embed mode when self-hosted.** Phase 0 only runs the editor. Embedding it in our
   screens is proved when phase 28 starts; pin the tested image version.
2. **Mayan sign-in through Keycloak.** Phase 0 runs Mayan with its own admin login
   (`EAX_MAYAN_ADMIN_USER` / `EAX_MAYAN_ADMIN_PASSWORD`). The Keycloak client `mayan` is already
   created. Next step: confirm whether the pinned Mayan version has an OpenID Connect option; if
   not, put Mayan behind an OIDC-aware proxy (for example oauth2-proxy) with remote-user sign-in.
3. **Mayan with Valkey (`dms-broker`) as its only broker.** Configured; confirm document upload and OCR jobs run.
4. **Superset row filtering by model.** Not needed until models exist (phase 5); the report login
   already sees only the `rpt` schema.
5. **Single sign-out.** Signing out of the start page ends the Keycloak session; check that Superset
   then asks to sign in again.
6. **Image versions.** The images in work/eaexplorer.env are a starting point; pin the versions that pass
   this checklist.

## If something does not start

- Every command writes `work/logs/eax-<date-time>-<command>.log`; a failed step adds diagnostics to it.
  `.\eax diag` writes a report at any time. Send that file when asking for help.
- `.\eax logs setup` - config problems (empty values, example passwords on a server) are listed here.
- `.\eax logs api` - migrations and the job runner.
- `.\eax logs reports-init` - Superset set-up and the sample import (a failed sample import is a
  warning only).
- `.\eax logs keycloak` - realm import. The realm is imported only when it does not exist yet.
- Ports 80 or 443 already in use: change `EAX_HTTP_PORT` / `EAX_HTTPS_PORT` in work/eaexplorer.env (for
  example 8080 / 8443) and run `.\eax up` again.
- Start again from nothing (deletes all data): `.\eax cleanup --all`, then `.\eax init laptop`
  and delete the `data` folder.
