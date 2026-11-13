# Where each database lives (R2.50, D611)

Every database EA Explorer uses has its own setting in `work/eaexplorer.env`. **Empty means the shared PostgreSQL** (the
`db` container), which is what a laptop and most servers use. Set one to move that database to a container or server of
its own, for space, speed or to keep it apart. Nothing else changes: the code reaches each database through its setting.

See them all: System Admin › Databases, or `eax databases` (what each holds, where it lives, whether it answers).

| Database | Setting | What it holds |
|---|---|---|
| repository | `EAX_DB_HOST`, `EAX_DB_PORT`, `EAX_DB_NAME` | the architecture: models, metamodels, entities, relationships, views |
| changelog | `EAX_CHANGELOG_DB_URL` | the change log (D180) |
| projects | `EAX_PROJECTS_DB_URL` | architecture projects (D266) |
| tests | `EAX_TESTS_DB_URL` | the self-test's runs, results and fixtures (R2.28) |
| operations | `EAX_OPERATIONS_DB_URL` | backups and schedules, deployments, jobs, health history (R2.27) |
| personal | `EAX_PERSONAL_DB_URL` | each person's settings, profile and skills, notifications, drafts (R2.53) |
| library_models | `EAX_LIBRARY_MODELS_DB_URL` | the read-only shared models (R2.42) |
| archive | `EAX_ARCHIVE_DB_URL` | archived and deleted models and projects (R2.41) |
| library | `EAX_LIBRARY_DB_HOST` | the reference and enterprise libraries' service (D410) |
| views | `EAX_VIEWS_DB_HOST` | the views service (D410) |
| keycloak | `EAX_KEYCLOAK_DB_HOST` | sign-in |
| reports | `EAX_SUPERSET_DB_HOST` | Reports (Superset) |
| documents | `EAX_MAYAN_DB_HOST` | Documents (Mayan) |

Connection strings are `postgresql://user:password@host:port/database`, the password URL-encoded (`^` is `%5E`, `&` is
`%26`). Hosts are a name (and `_PORT` beside it when not 5432). A server of its own is reached by backups as `postgres`
with the same superuser password as the shared one.

## Schemas, not databases (D630)

The parts of the repository that can move are **schemas** in the one repository database, not databases of their own
(owner, 13 Nov 2026: one PostgreSQL, one database, so a laptop does not run many database servers). No database or
server is ever created for them:

| Part | Schema | Setting | Tables |
|---|---|---|---|
| tests | `tests` | `EAX_TESTS_DB_URL` | test_runs, test_results, test_fixtures (R2.28) |
| operations | `operations` | `EAX_OPERATIONS_DB_URL` | backup_schedules, deployments, update_history, heartbeat_logs, startup_parts (R2.27) |
| archive | `archive` | `EAX_ARCHIVE_DB_URL` | archive_store: each archived or deleted model or project as its backup file (R2.41, D628) |
| personal | `personal` | `EAX_PERSONAL_DB_URL` | each person's notifications, requests, favourites, saved views, skills, settings (R2.53) |
| library_models | `library_models` | `EAX_LIBRARY_MODELS_DB_URL` | the library models' content (entities, relationships, values, metamodel, history; their rows stay in core.models), moved in at start-up (R2.42, D633). Elsewhere: the directory tables the screens join are copied beside it |

Each has its own connection string. **Empty** (the default): its schema in the repository database, the same connection
as the rest. **Scaling one out** is changing only its location: point its setting at another PostgreSQL database that
already exists, run `eax up` (at start EA Explorer makes the schema and its tables there from the migrations'
description), then `eax databases copy KEY` to bring the rows that are here. The code always names a table with its
schema (`tests.test_runs`), so nothing else changes. The runs' fixtures (the self_test models, projects and accounts)
stay in the repository, as they test it. The sample Reports dashboard of heartbeats reads the repository database.

## Moving one

1. Take a backup: `eax backup before-moving`.
2. For a schema (the table above): the target database must already exist (EA Explorer does not create one); set its
   setting in `work/eaexplorer.env`, run `eax up`, then `eax databases copy KEY`.
3. For a service's own database (library, views, Keycloak, Reports, Documents): `pg_dump -Fc` from the shared server,
   `pg_restore` into the new one, set its setting, `eax up`.
4. Check: `eax databases` says it answers, at its new place.

Backups follow each database to where it lives (`services/backup/servers.sh`): a backup dumps it from there and a
restore puts it back there. To bring one back to the shared server, empty its setting after copying it back.
