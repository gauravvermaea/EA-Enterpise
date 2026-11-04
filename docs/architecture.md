# How EA Explorer is built

Technical documentation for developers and AI agents picking up the work. What the product does is
in the [requirements](requirements) and the phase notes (`phase-N.md`); why things are as they are is
in [decisions.md](decisions.md); the database in detail is in [database.md](database.md). Start with
[../AGENTS.md](../AGENTS.md) if you are an agent.

## The containers

One Docker Compose stack (`docker-compose.yml`, plus `deploy/compose/docker-compose.laptop.yml` or
`.server.yml`), configured by one file, `work/eaexplorer.env`, made by `eax init` from
`deploy/templates/eaexplorer.<kind>.env`.

| Service | What it is | Built from |
| --- | --- | --- |
| `proxy` | nginx: TLS, routes `/` to web, `/api` and `/mcp` to api, `/auth` to Keycloak, reports.* and docs.* hosts | `deploy/proxy/templates/default.conf.template` |
| `web` | The React screens, built by Vite, served by nginx | `services/web` |
| `api` | Flask REST API (gunicorn, port 8000), the job runner (Procrastinate) and the MCP server (uvicorn, port 8001), side by side, reached only through nginx; runs migrations and the seed on start | `services/api` (`entrypoint.sh`) |
| `setup` | One-off: certificates, Keycloak realm, Superset sample | `services/api` (`python -m eax.setup`) |
| `db` | PostgreSQL 16: databases `eaexplorer` (repository), `keycloak`, `superset`, `mayan` | `deploy/postgres/initdb` |
| `keycloak` | Sign-in (OIDC); realm `eaexplorer` from `deploy/keycloak/realm-eaexplorer.json.tmpl` | image |
| `reports`, `reports-init` | Apache Superset | `deploy/superset` |
| `dms`, `dms-broker` | Mayan EDMS and its Valkey broker | image |
| `drawio` | Self-hosted draw.io | image |
| `backup` | Database dumps and Mayan files to `/backups`; `eax backup` / `eax restore` | `services/backup` |

## The API (`services/api`)

```
eax/
  app.py            Flask app factory, flask-smorest Api, blueprints, request ids, logging
  config.py         settings from the environment (EAX_*)
  auth.py           token check (require_auth(permission)), Keycloak roles mapped to ours, break-glass tokens
  permissions.py    the one permission check (roles, permissions, test users) for REST and MCP
  keycloak_admin.py reads people and roles from Keycloak (the API's own client, eax-admin)
  db.py             SQLAlchemy engine (psycopg 3)
  repository.py     ALL reads of models, metamodel, entities, history, graphs, checks: one function
                    per question, shared by REST and MCP
  metamodel_edit.py ALL metamodel writes: apply(conn, model, op, payload, actor, dry_run) and locks
  rules.py          the validation rules engine: evaluate() warns, never blocks (D48)
  diagram.py        Mermaid ER diagrams of the metamodel
  sqlconsole.py     the read-only SQL window (every run rolled back, D52)
  audit.py          audit log writes
  mcp_server.py     MCP tools: thin wrappers over repository functions
  jobs.py, jobs_schema.py   Procrastinate job queue
  versioning.py     version.toml and core.schema_version() must agree (heartbeat warns)
  health.py         service health for the heartbeat
  api/              REST blueprints: heartbeat, me, jobs, audit, metamodel (reads),
                    metamodel_edit (phase 3 writes), sql; schemas.py holds marshmallow schemas
  seed/             ArchiMate 4 template, insurance reference model, sample model (rows)
  setup/            first-start setup (TLS, Superset sample)
migrations/         Alembic; versions/000N_*.py, big SQL in migrations/sql/000N_*.sql
tests/              pytest (no database needed) and tests/sql/phaseN_checks.sql (need the database)
version.toml        the API's version; must equal the newest core.schema_versions row
```

**The pattern for a new feature**: add the query or change to `repository.py` (reads) or a module
like `metamodel_edit.py` (writes), expose it from a blueprint in `eax/api/` with marshmallow schemas
(it then appears in Swagger at `/api/docs`), add an MCP tool in `mcp_server.py` when an agent would
use it, and a screen in `services/web/src`. Writes run in one transaction (`_write` in
`api/metamodel_edit.py`): rolled back for a dry run, otherwise audited and committed.

**Who may do it**: every view is wrapped in `require_auth(permission)` (403 first), and the
signed-in person is set on each database connection (`eax.actor`, `eax.user_roles`, in `db.py`), where
row-level security and triggers enforce the same rules (migration 0006). MCP tools do the same and
refuse to run without a known person.

**Who did it**: every write sets `eax.actor` (`set_config('eax.actor', user, true)`); triggers stamp
`created_by` / `modified_by` and the history from `core.current_actor()`. `eax.history_label`
labels the history rows a transaction writes (the metamodel editor sets `metamodel vN`).

## The database (`eaexplorer`)

Summary; details in [database.md](database.md).

- Schemas: `core` (models, metamodel, content), `history` (`row_versions`, written by the trigger
  `history.capture` on every table), `eax` (functions such as `eax.get_entity(type, name)`), `audit`,
  staging and jobs.
- Conventions: every table has a bigint `id` and a `guid` (uuid, what the API shows); table names are
  plural, foreign keys singular with `_id`; housekeeping columns `status_code`, `is_deleted`,
  `created_at/by`, `modified_at/by`, `row_version`. Nothing is hard-deleted: `is_deleted` plus history.
- Each model owns its metamodel (layers, entity types, attribute types, item attributes, pick lists,
  relationship types, allowed relationships, validation rules) and its content (entities, attribute
  values, relationships).
- Locks: `is_locked` (installer's permanent lock on templates and reference models; only the login
  `eax_migrator` passes) and `lock_level` (model locks set by people, phase 3). Both enforced by
  triggers, so every route (screens, API, MCP, psql) obeys them.
- Versions: `core.schema_versions` (database), `core.metamodel_versions` (each model's metamodel).

## The screens (`services/web/src`)

React 18, Vite, no router library: the hash is the route (`#/metamodel/<model>/<tab>/<item>/<sub>`,
parsed in `App.jsx` and `Metamodel.jsx`). `auth.js` signs in with keycloak-js and `apiFetch` adds the
token. Main files: `StartPage.jsx`, `Metamodel.jsx` (model page and its tabs), `ModelViews.jsx`
(type tables, entity page, `useApi`, `refreshAll`), `MetamodelEditor.jsx` (phase 3 dialogs, history,
failing checks, locks), `EntityGraph.jsx`, `HierarchyMap.jsx`, `RelationMatrix.jsx`,
`MetamodelDiagram.jsx` (elkjs layouts), `exporting.js` (CSV, SVG, PNG, .drawio), `Sql.jsx`, `Mcp.jsx`,
`Library.jsx`, `ModelSwitcher.jsx`. Styles in one `styles.css`.

## Building and testing

The user runs Docker; agents write code (see AGENTS.md).

| What | Command |
| --- | --- |
| Start clean (always, D54) | `.\eax clean-run` (Windows) or `./eax.sh clean-run` |
| Start and record container logs | `.\eax clean-debug` |
| Logs, diagnostics | `work/logs/`; `.\eax diag` |
| Python tests | `cd services/api; pip install -r requirements-dev.txt; pytest -q` (CI also runs `ruff check .`) |
| Database checks | `Get-Content services/api/tests/sql/phase4_checks.sql \| docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1` (and phase 1, 2 as postgres; 3, 3.1 as eax_app) |
| Web build | `cd services/web; npm install; npm run build` |
| API explorer | `https://localhost/api/docs` |

`tests/sql/phaseN_checks.sql` each run in a transaction that is rolled back and end with
"phase N checks passed". Every phase adds one.

## Versions and migrations

Phase N is version 0.N.0; additions between phases take a patch number (0.2.1). A phase adds one
Alembic migration `000N_<name>` which inserts its row into `core.schema_versions`; `version.toml`
moves with it. Accepted migrations are never edited; the next phase adds a new one.
