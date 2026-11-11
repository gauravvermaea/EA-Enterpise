# Operations (phase 0)

## Everyday commands

Every command, and the console for getting a system that is down back up (`.\eax console`), is described in
detail in [command-line-and-console.md](command-line-and-console.md).

Run `.\eax help` (Windows) or `./eax.sh help` (Linux / macOS) for a description of every command, or
`.\eax help <command>` for one. On Windows, `.\eax` runs `eax.ps1` with the execution policy bypassed
for that run (the script is not signed); the long form is
`powershell -NoProfile -ExecutionPolicy Bypass -File .\eax.ps1 <command>`.

| Task | Windows | Linux / macOS |
| --- | --- | --- |
| First set-up | `.\eax init laptop` | `./eax.sh init laptop` |
| Start or update (the core first, the rest in the background) | `.\eax up` | `./eax.sh up` |
| Start and wait until everything is up | `.\eax up --wait-all` | `./eax.sh up --wait-all` |
| Start again from scratch | `.\eax clean-restart` (add `--wait-all` to wait for everything) | `./eax.sh clean-restart` |
| Start and keep recording container logs | `.\eax debug` | `./eax.sh debug` |
| Diagnostics report | `.\eax diag` | `./eax.sh diag` |
| Status | `.\eax status` | `./eax.sh status` |
| Logs | `.\eax logs api` | `./eax.sh logs api` |
| Stop (data kept) | `.\eax down` | `./eax.sh down` |
| Backup now | `.\eax backup` | `./eax.sh backup` |
| Show logins (laptop) | `.\eax logins` | `./eax.sh logins` |
| Trust the local certificate (optional, once) | `.\eax trust` | `./eax.sh trust` |
| Remove that trust | `.\eax trust --remove` | `./eax.sh trust --remove` |
| Empty the work folder (keeps the certificate) | `.\eax cleanup` | `./eax.sh cleanup` |
| Empty it and delete the databases | `.\eax cleanup --all` | `./eax.sh cleanup --all` |
| Also delete the certificate | `.\eax cleanup --all --certificate` | `./eax.sh cleanup --all --certificate` |
| List backups | `.\eax backups` | `./eax.sh backups` |

## How EA Explorer starts (phase 12.1, D255)

A start used to wait for everything, one part after another, and took five to seven minutes. It now starts in **two
tiers**, so you can sign in as soon as the core is ready (usually one to two minutes):

| Tier | What | When |
| --- | --- | --- |
| **1st, the core** | `db` (PostgreSQL), `setup`, `proxy` (nginx), `web` (the screens), `keycloak` (sign-in), `api` (every copy) with the database upgrade and the built-in models (ArchiMate 4, the insurance reference model, views, the laptop test users' roles) | `eax up` waits for it: the API and Keycloak must say *healthy* |
| **2nd, after the core** | `reports-init` and `reports` (Superset), `dms-broker` and `dms` (Mayan), `drawio`, `backup`, `ops` (the operations helper) | started in the background as soon as the core is ready |
| **2nd, inside the API** | the sample insurance model, the laptop test models (Fynbos, Karoo Re, Lean EA and the models in each state), the demo estate Protea Insurance, the data quality samples, the History tab samples, the demo estate's tags, gap analyses and sheets, then **each model's first data quality measurement** | loaded one step at a time by `eax/seed/later.py`, after the API has started; each model appears as soon as its step is done |

What `eax up` does (`run` is the same):

1. Starts the core and shows each change while it waits: `eaexplorer-api-1: starting`, then `healthy`.
2. Says **"EA Explorer is ready after N s: you can sign in."**
3. Starts the second tier in a hidden window of its own (log: `work/logs/eax-<time>-start-later.log`) and returns, so the
   window is free at once.

**`--wait-all`** (on `up`, `run`, `debug`, `clean-run`, `clean-debug` and `clean-restart`): starts the second tier in
the same window and waits until **everything** is up (Reports, Documents, Diagrams and the sample data), showing each
change, for up to 30 minutes. Use it before a demo or a test that needs everything, or in a script:

```
.\eax up --wait-all
.\eax clean-restart --wait-all
./eax.sh up --wait-all
```

Naming services (`eax up api proxy`) starts only those, as before, with no tiers.

**What people see while the second tier starts.** Everyone sees the start-up status in the header:

| Colour | Word | Meaning |
| --- | --- | --- |
| green | up | it answers (or the work is done) |
| amber | starting | its container is starting or setting up, or the sample data is loading (*loading 3 of 9*) |
| red | down | its container stopped or failed, or a step of the sample data failed (the next start tries it again) |
| grey | off | switched off (Administration > System settings > Services) |

When everything is up the header shows a single green **All up**. Click it for each part with what it is doing; IT and
Super Admins also get **Every container →**, which opens Administration > Containers. There each container has a
**Start-up** column: up, starting or down, and **1st** (the core) or **2nd** (after it). A line at the top shows every part.

**Open in draw.io** (D256) while draw.io is still starting opens a tab that says so: close it and try again in a moment.

**Reports** wait for the sample data before adding their typed datasets (one per entity type in use), so every type is
there; they wait at most 15 minutes, then add what is there (the rest at the next start).

**Several API servers** (D249): every copy belongs to the core; one of them loads the second tier inside the API, and the
others skip it.

The start-up status is also readable without signing in at `/api/startup` (the parts and their states only), and with
details at `/api/v1/startup` (signed in; the containers for IT and Super Admins).

## One-time task: the TOGAF templates (phase 13, D262)

Architecture projects start their documents from templates. The TOGAF templates belong to The Open Group, so EA
Explorer ships only their names; a Super Admin loads the licensed files once, after the first start:

1. Download **The TOGAF Standard, 10th Edition: Template Deliverables** (The Open Group publication I094) from
   <https://publications.opengroup.org/i094>.
2. (Only for the folder way) Unzip it into `library/templates/togaf` in the EA Explorer folder, keeping its folders. To keep it elsewhere, set
   `EAX_LIBRARY_DIR` in `work/eaexplorer.env` to a folder holding `templates/togaf` and restart. Git ignores the files;
   the API reads the folder read-only (`/data/library`).
3. Sign in as a Super Admin: **Administration > Project library > ⬆ Upload the TOGAF zip** and choose the zip as you
   downloaded it; or unzip it into the folder above and press **Load templates from the folder**. Each file that
   matches a TOGAF template is stored in Documents unchanged. A single template can be uploaded on its own line.

Once the files are in the folder, each start loads any TOGAF template without its file automatically (in the
background, as soon as Documents is up), so a clean restart, which empties Documents, needs no hand work.
`eax up` shows these steps until the folder holds the files. Documents must be up (green in the header) to load them.

**Then finish the template library setup** (D264), on the same page: tick the template libraries to offer to projects
(EA Explorer's own, TOGAF 10, and any of your own: download a library's zip, rebrand it, add documents and upload it
under a new name) and press **Finish the setup**. Nobody can create a project until this is done.

## The work folder and logs

`work/` holds everything local and is never committed: `work/eaexplorer.env` (the config),
`work/logs` (one log per command, kept 14 days; `containers-*.log` from `debug`) and, on a laptop,
`work/data` (backups, imports, exports, tls). Database and document data live in Docker volumes,
which `cleanup --all` deletes. Passwords and secrets are masked in diagnostics and container logs.

## Backups (phase 8.4, D216)

Three kinds (the project backup added on 7 Nov 2026), all in **`work/backups`** on every installation (not configurable; to keep them on a file server or other
disk, mount it at `work/backups`, D226), both listed on **Administration > Backups**:

```
infrastructure/20261106T010000Z-nightly/          one infrastructure backup (tagged)
  databases/<name>.dump  globals.sql              every database (pg_dump custom format) and the logins and roles:
                                                  eaexplorer, keycloak, superset, mayan, eaxlibrary, eaxviews
  databases/HOSTS  globals-<name>.sql             the library's or views' database when it is on a server of its own
  files/documents.tar.gz  files/tls.tar.gz        Mayan's document files, the site certificate
  files/reports.tar.gz                            the reports' home (Superset's secret key and uploads)
  files/imports.tar.gz  files/exports.tar.gz      the API's import and export folders
  config/eaexplorer.env  services.env             the config file as it was
  code/release.json  docker-compose.yml  deploy/  the release version, image names and digests, the compose files
  SHA256SUMS  manifest.json  [PINNED]
application/20261106T093000Z-end-of-quarter/      one application backup: every model and every project
  manifest.json  models/<model>.eaxbackup.zip  projects/<project>.eaxproject.zip
  organisation.eaxorg.zip                         what belongs to no model or project (D410)
application/models/<model guid>/...               a model's own backups (made on its Backups tab)
application/projects/<project guid>/...           a project's own backups (its About tab, or Administration > Backups)
application/uploaded/...                          files brought from another installation
```

* **Schedules** are set on Administration > Backups > Schedules by IT and Super Admins (kept in the database, never in
  the config file, D222): on or off, when (in the installation's time zone), the tag, how many to keep, when the health
  check warns. Defaults: infrastructure every day at 01:00, application every Sunday at 02:00; both on.
* **Infrastructure**: on its schedule and on demand (`.\eax backup <tag>` or Back up now). The operations helper runs
  it; people keep working. It holds **all of Documents**: Mayan's database (`databases/mayan.dump`) and every version
  of every document file (`files/documents.tar.gz`); the Holds column shows **✓ Documents**. Restoring it with
  *full* or *app+data* (on the screen, or `.\eax restore <name> --what full|app+data`), or *files* (Documents' files with its own database, the certificate, the reports' home, the import and export folders),
  puts Documents back as it was.
* **What each backup carries** (owner, 10 Nov 2026, D410):

  | Backup | Carries |
  |---|---|
  | Infrastructure | Every database (the main one, Keycloak's, Superset's, Mayan's, the library's and the views', each from the server it is on), the logins and roles, Documents' files, the certificate, the reports' home, the import and export folders, the config file, the release and compose files. Its `manifest.json` lists what is in it (`contents`) and what is not and why: `eax-pgdata` (the databases are in it as dumps), `eax-rendered` and `eax-kc-import` (made again from the config file at every start) |
  | Model backup (and package) | Entities, relationships, the metamodel (with each end's multiplicity and each type's notation and colour), the history, every drawn view with its versions, the model's own views, the entities' own icons, an Excel workbook; put back over itself, its views and icons come back too; into another installation, each view's shapes are bound to the new model's entities |
  | Project backup | The project's rows (documents with their files from Documents, canvases, key questions, stakeholders, placeholder views, the links from views to evidence, ...), its models, its library |
  | Organisation part (in a full application backup) | The organisation's own views and project templates, people's skills, the architecture board, the enterprise library, the organisation reference library (its rows and files) |

  A restore puts back databases first, then the file sets, then starts the services. On a new server the logins and
  roles a database needs are made from the backup first. Backups made before 10 Nov 2026 still restore: they have no
  reports' home or import and export folders (what is there now stays, and the restore says so), and an application
  backup without the organisation part restores its models and projects as before.
* **Application**: on demand (Back up every model now). A **model backup file** (`.eaxbackup.zip`) holds the deep model
  package (metamodel, content, history), the model as an Excel workbook, and what is needed to put the model back over
  itself. Model Admins back up their own model on its **Backups** tab. A full application backup also holds **every
  project** as a project backup file (without its models, which are beside it) with the latest version of each of its
  documents. **Restore all** (on the screen, or `.\eax restore-app`) puts the models back, then every project over itself
  (or made again when it is gone): its rows go back as they were, its repository is built again in Documents, and each
  document still there gets the backed-up file as its newest version when it differs; one that is gone is uploaded again.
* **Project**: one project with its models and documents (`.eaxproject.zip`), made on the project's About tab by its
  Project Admins or on Administration > Backups > Project backups. Restored as a **new project**, or by a Super Admin
  **over itself** (its own models put back as they were too). Project Admins, Lead Architects, IT and Super Admins back
  projects up and restore them as new ones. The newest of each project's are kept as for models.
* **Kept**: the newest of each kind as set in its schedule (and the same number of each model's own); the oldest go
  after each backup. **Pinned** backups are never removed (the backup taken before a restore or an upgrade is pinned).
* `.\eax backups` lists the infrastructure backups.

## Backup and restore from the command line (D227)

Everything the console does with backups can be done with the `eax` command, which works when the console cannot (it
starts the database, the backup container and the operations helper if they are not running). Windows: `.\eax ...`;
Linux and macOS: `./eax.sh ...`.

| Command | What it does |
|---|---|
| `eax backup [tag]` | An infrastructure backup now, tagged |
| `eax backups [words]` | Every backup: infrastructure (numbered) and application; with words, those whose tag, name or maker has them |
| `eax restore` | Lists the infrastructure backups to choose from, asks what to restore (full, app, app+data, db, files) and for RESTORE, then restores, showing every step |
| `eax restore <name\|tag\|latest> --what full [--yes]` | The same without questions (for scripts); a tag picks the newest good backup with it, `latest` the newest good one; it says which it chose |
| `eax restores` | Every restore (infrastructure and model) with its status |
| `eax stop-backup` | Stops the backups running (infrastructure at once, application after the model it is on); the partial backup is deleted. A restore cannot be stopped |
| `eax restore-app [run\|tag\|latest] [--yes]` | Every model of an application backup put back over itself; models no longer there made again; newer ones left as they are; then every project in it over itself with its documents (the api container must run) |
| `eax maintenance on\|off` | Shows the maintenance page to everyone (or stops showing it) |
| `eax restore-log <id>` | A restore's whole log |
| `eax delete-backup <name>` | Deletes an infrastructure backup (unpin it first) |
| `eax delete-restore <id>` | Forgets a finished restore and its log |
| `eax app-backup [tag]` | Backs up every model and every project with its documents now (an application backup) |
| `eax restore-model` | Lists the application backups and their models to choose from, then restores one as a new model or over itself (the api container must run) |

## Restore

**From the console** (IT and Super Admins): Administration > Backups > **Restore...** on a backup: choose what, type
RESTORE. The restore then runs **on its own** in the operations helper; the console does not wait for it (large restores
take hours). Every screen shows a **lock page** to everyone until it has finished (it asks the proxy, not the API, which
may be stopped); whoever started it follows its log there and on **Administration > Restores**, which lists every
restore with its status and whole log (newest first; delete finished ones by hand). Model restores (Restore... on an
application or model backup) run as tasks and are listed there too, and on the model's Backups tab.

**The maintenance page** (D230): while a restore runs, while `eax up` rebuilds a running installation, or after
`eax maintenance on`, the proxy answers everyone with a plain "EA Explorer is under maintenance" page (and the API with a
short JSON answer); it also shows whenever EA Explorer is starting. It checks every 15 seconds and opens EA Explorer again
when it is back. It is switched on by the file `work/proxy/maintenance`.

**Stopping a backup** (D231): **Stop** on Administration > Backups or `eax stop-backup`. An infrastructure backup stops at
once, an application backup after the model it is on; the partial backup is deleted. A restore cannot be stopped.

**Models are locked while they are restored** (D236): a model put back over itself is locked for the person restoring until it is done; others see the lock and cannot change it.

**A whole application backup** (D233): **Download all** on an application backup gives every model in one file
(`.eaxapp.zip`), to keep or to upload on another installation (Upload a backup file). **Restore all** (Super Admins) puts
every project model back over itself, makes again a model that no longer exists, and leaves the rest as it is.

**How a restore keeps the installation safe** (D227):

1. A backup of the current state is taken first, pinned.
2. The maintenance page goes on first (D237); everyone is told; every service but the database, the backup container, the operations helper and the proxy stops (D230).
3. Every database is restored into `<name>__restoring` and every file set unpacked beside the live files, stopping at
   the first error: until then **nothing live has changed**, and a failure leaves the installation as it was.
4. Only then are they swapped in (the live database's owner, grants and settings kept); if a swap fails, the ones
   already swapped are put back.
5. The services start again, the proxy restarts if the certificate was restored, Keycloak restarts (everyone signs in
   again), maintenance ends. Everything is in the restore's log: `work/backups/restores/<id>/restore.log`.

**Everyone is told** (D229): when a restore starts, everyone gets a notification and the webhooks are sent at once; when it ends (finished or failed), everyone is told again within a minute of EA Explorer being back.

**Restores can be repeated** (idempotent, D228): restoring the same backup again gives the same result; a restore first
puts right what an interrupted one left (a database left renamed, files left aside); a restore cut off (the helper or
the eax command stopped) is marked interrupted and the lock page goes. Restoring a model backup as a new model again
makes another copy with a numbered name.

A backup from a newer version than the one running is refused for the databases (install that release first). After a
partial restore (db or files) a warning says documents and their records may no longer match. To try a backup without
touching live data: `docker compose --env-file work/eaexplorer.env exec backup restore.sh infrastructure/<name> --scratch`.

**A model** (application or model backup): restored as a new model (Model Creators, Super Admins; under its root
metamodel when that matches, otherwise as a root of its own; a draft), or put back over itself (its Model Admin,
typing its name): what it is now is kept first, as a model backup and a tag, and the backup becomes one commit of kind
restore. A file from another installation is uploaded on Administration > Backups.

**Clean-up**: `eax cleanup` (and `clean-restart`) deletes the work folder, **every backup and restore log included**;
copy `work/backups` elsewhere first to keep them.

## Services on and off (D191)

Every optional service is on unless the config file says off: `EAX_SERVICE_REPORTS`, `EAX_SERVICE_DOCUMENTS`,
`EAX_SERVICE_DRAWIO`, `EAX_SERVICE_MCP`, `EAX_SERVICE_CHANGE_LOG`, `EAX_SERVICE_BACKUPS`. `eax services` lists them and
their containers; `eax service <name> on|off` switches one: it keeps a dated copy of the config file in
`work/config-history`, writes the switch and starts or stops the containers. A Super Admin does the same in
Administration > System settings > Services, and restores an earlier copy of the config file there. The switches (no
secrets) are also written to `work/services.env`, which the API reads. `eax up` creates switched-off containers without
starting them.

## API and job servers (D249)

The api container answers API calls and runs the background jobs (data quality measurements among them). Run more
copies of it when jobs queue up or the screens slow down: `.\eax servers` shows them, `.\eax servers 3` runs three
(a dated copy of the config file is kept first; `EAX_API_SERVERS` in the config file; laptop default 1, server 2), at
once and without a restart. Super and IT Admins do the same on Administration > Containers with + and −. nginx spreads
API calls across every copy within seconds. Removing one stops the highest-numbered copy, giving the jobs it runs two
minutes to finish; the first is never removed. At start the copies apply the database upgrade one at a time (the first
does the work), and the change log is shipped by one copy only (another takes over if it stops). With more than one,
each is named **api-1**, **api-2**... on Administration > Containers: its properties, logs, terminal and commands are
its own. The number is kept in the config file (`EAX_API_SERVERS`), so `eax restart`, `eax up`, `eax run` and
`eax clean-restart` keep it; an infrastructure restore that puts the config file back keeps the current number too.

## Scaling out (phase 36.3, D520, D521, D526 to D528)

**System admin, Scaling** sets the number of API servers, fixed or by rules (people active and CPU, one server at a
time with a cool-down); the operations helper applies it every minute and logs why. More hosts, a database standby
(`eax standby status|promote`), shared storage on NFS and the library on its own server are compose overlays named in
`EAX_COMPOSE_EXTRA`. See [phase-36.3.md](phase-36.3.md).

## The self-test (phase 36.1, D522 to D525, D529)

`eax test` or **System admin, Self-test** tests this installation in fixtures of its own (`self_test_<id>_n`), with a
report at the end; fixtures stay until purged by hand (`eax test --clean <run|all>`). See [testing.md](testing.md).

## The operations helper

The `ops` container (phase 10) lets a Super Admin restart the system from Administration > System settings. It
reaches the Docker engine through `/var/run/docker.sock`, is only on the internal network, publishes no port, and
answers only with the shared secret `EAX_OPS_TOKEN` (set a long random value on a server; the setup refuses the laptop
one there). It only restarts this installation's containers. If it is not running, the console says so; `.\eax restart`
still works.

## The change log's database

The change log (phase 9) has its own connection string, `EAX_CHANGELOG_DB_URL`
(`postgresql://user:password@host:port/database`, the password URL-encoded) and schema, `EAX_CHANGELOG_DB_SCHEMA`
(default `changelog`). Empty means the repository's database. On a server, point it at another database or server so
the log never competes with the repository; the login must be able to create the schema and its two tables (or have
them made for it). The api container's log shows `EA Explorer change log WARNING` lines when it cannot reach it; the
repository keeps working and the log catches up once it can.

## The architecture projects' database (D266)

Architecture projects (schema `proj`) have their own connection string, `EAX_PROJECTS_DB_URL`
(`postgresql://user:password@host:port/database`, the password URL-encoded). Empty, the usual, means the repository's
database, where the upgrade makes the schema; creating a project and its models is then one transaction. No foreign key
and no query crosses from `proj` into the other schemas (models are kept by their guid), so the schema can be moved:
stop EA Explorer, copy it (`pg_dump -n proj` into the new database), set `EAX_PROJECTS_DB_URL` and start again. The
seed then keeps the project library up to date there. Backups (D216) cover the repository's database only: a moved
`proj` database needs its own backups until that is added.

## Machine access (phase 25, D366)
Tokens, API keys and client certificates are managed on **System admin › Machine access** ([phase-25.md](phase-25.md)).
Client certificates use mutual TLS on the proxy's own port, `EAX_MTLS_PORT` (9443 unless set in `work/eaexplorer.env`):
open it in the firewall only for the systems that need it. Browsers never use that port. If a credential leaks, revoke it
there (or disable its service account): it stops at once.

## Operations insight and housekeeping (phase 35, D371)
**System admin › Operations** ([phase-35.md](phase-35.md)) shows usage, idle models (a report only), stale work, database
health and the archive. Prometheus reads `https://<host>/api/metrics` with a token that may read Administration (an IT
Admin's, or a service account with the IT Admin role).

Housekeeping runs every night at 02:40 but changes nothing until an IT Admin or Super Admin confirms a dry run of the
retention rules (Operations › Housekeeping); changing a rule asks for a new dry run. The defaults only archive (loads and
task files after 90 days, notifications after a year); nothing is deleted until an admin sets a rule to delete. Old
history versions are kept unless a Super Admin sets an age in years; then versions older than that are removed after a
confirmed dry run, never the current ones or any a tag, baseline, merge starting point, drawn view evidence or governance
record needs (D445).

## Settings that survive resets (D558)

`cleanup`, `clean-run` and `clean-restart` delete the work folder and every database. A few settings must outlive
that, for example a demo that resets itself every night and must keep its schedule. They live in **`persist/`**, a
folder beside `work/` (set `EAX_PERSIST_DIR` in the config file for another folder) that no command ever deletes:

| File or folder | What it holds |
|---|---|
| `persist/schedules.json` | Scheduled eax commands (System admin > Command centre > Schedules, `eax schedule`) |
| `persist/banner.json` | The banner under the top bar (System admin > Banner) |
| `persist/safety-backups/` | The backup taken before a command that deletes everything (scheduled ones keep their newest N) |
| `persist/test-results/` | The reset-survival test's results (`eax test --reset-survival`) |

The JSON files are the source of truth: the operations helper reads them whenever it needs them and writes them
atomically (a temporary file, then a rename) when an admin changes something on the web or with `eax schedule`. You can
read and edit them by hand. If a file does not parse, its last good copy (`<name>.bak`) is used and the System admin
pages show a warning; save the settings again or fix the file. `persist/` is in every infrastructure backup (its
`safety-backups/` left out), never in git (`.gitignore`).

`persist/schedules.json`:

```json
{
  "version": 1,
  "_comment": "Scheduled eax commands (D559). Survives resets. ...",
  "schedules": [
    {"id": "0d3m01", "name": "Demo reset every night", "argv": ["clean-restart", "laptop"], "cron": "0 2 * * *",
     "enabled": true, "created_by": "user_super_admin", "created_at": "2026-11-10T22:55:00+02:00",
     "wipe": true, "backup_first": false, "keep": 3, "banner": true,
     "confirmed": {"by": "user_super_admin", "at": "2026-11-10T22:55:00+02:00", "installation": "demo-laptop"},
     "last": {"run": "20261111T000000Z-sched0d3m01-1a2b", "at": "2026-11-11T02:00:10+02:00", "state": "started"}}
  ]
}
```

`persist/banner.json`:

```json
{
  "version": 1,
  "_comment": "The banner under EA Explorer's top bar (D558). Survives resets. ...",
  "banner": {"text": "This demo resets every day at 02:00: everything entered is deleted then.", "link": "",
             "link_text": "", "level": "info", "audience": "everyone", "dismissible": true,
             "starts": null, "ends": null, "by": "user_super_admin", "at": "2026-11-10T22:55:00+02:00",
             "source": "schedule:0d3m01"},
  "history": []
}
```

Remove `"banner"` (or set it to `null`) and nothing is shown.

## The banner and schedules (D558, D559)

System admin > **Banner** sets one message under the top bar (nothing shows when none is set); System admin > Command
centre > **Schedules** runs eax commands by themselves, e.g. a nightly backup or a demo that resets every night. Both
are kept in `persist/` and survive resets; see command-line-and-console.md.

## Moving to a server

Run `./eax.sh init server` on the server, set the host name, and certificate folder in
`eaexplorer.env`, replace every `change-me` value with your own passwords (the helper does not generate
them; the development password `P^55w0rd1234&` is refused on a server), start once, then restore a backup taken on the laptop. Deployment scripts for every
kind arrive in build phase 36.
