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

## The self-test's database (R2.28)

The self-test's runs, results (with their screenshots) and fixtures records can live in a database of their own: set
`EAX_TESTS_DB_URL` and run `eax up`. At every start EA Explorer makes the tables there, or brings them in line, from
the shared database's (the migrations keep those, so they stay the one description of each table, and they are left
empty and unused). Then `eax databases copy tests` brings the runs made before (rows already there are kept). The
runs' fixtures (the self_test models, projects and accounts) stay in the repository, as they test it.

## Moving one

1. Take a backup: `eax backup before-moving`.
2. Make the database on the new server (a container in docker-compose.override.yml, or a managed PostgreSQL), with the
   same login and password as on the shared server.
3. Copy it: `pg_dump -Fc` from the shared server, `pg_restore` into the new one.
4. Set its setting in `work/eaexplorer.env` and run `eax up`.
5. Check: `eax databases` says it answers, at its new place.

Backups follow each database to where it lives (`services/backup/servers.sh`): a backup dumps it from there and a
restore puts it back there. To bring one back to the shared server, empty its setting after copying it back.
