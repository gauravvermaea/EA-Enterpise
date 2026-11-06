# Operations (phase 0)

## Everyday commands

Run `.\eax help` (Windows) or `./eax.sh help` (Linux / macOS) for a description of every command, or
`.\eax help <command>` for one. On Windows, `.\eax` runs `eax.ps1` with the execution policy bypassed
for that run (the script is not signed); the long form is
`powershell -NoProfile -ExecutionPolicy Bypass -File .\eax.ps1 <command>`.

| Task | Windows | Linux / macOS |
| --- | --- | --- |
| First set-up | `.\eax init laptop` | `./eax.sh init laptop` |
| Start or update | `.\eax up` | `./eax.sh up` |
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

## The work folder and logs

`work/` holds everything local and is never committed: `work/eaexplorer.env` (the config),
`work/logs` (one log per command, kept 14 days; `containers-*.log` from `debug`) and, on a laptop,
`work/data` (backups, imports, exports, tls). Database and document data live in Docker volumes,
which `cleanup --all` deletes. Passwords and secrets are masked in diagnostics and container logs.

## Backups (phase 8.4, D216)

Two kinds, both in **`work/backups`** on every installation (not configurable; to keep them on a file server or other
disk, mount it at `work/backups`, D226), both listed on **Administration > Backups**:

```
infrastructure/20261106T010000Z-nightly/          one infrastructure backup (tagged)
  databases/<name>.dump  globals.sql              every database (pg_dump custom format) and the logins and roles
  files/documents.tar.gz  files/tls.tar.gz        Mayan's document files, the site certificate
  config/eaexplorer.env  services.env             the config file as it was
  code/release.json  docker-compose.yml  deploy/  the release version, image names and digests, the compose files
  SHA256SUMS  manifest.json  [PINNED]
application/20261106T093000Z-end-of-quarter/      one application backup: every model as a model backup file
  manifest.json  models/<model>.eaxbackup.zip
application/models/<model guid>/...               a model's own backups (made on its Backups tab)
application/uploaded/...                          files brought from another installation
```

* **Schedules** are set on Administration > Backups > Schedules by IT and Super Admins (kept in the database, never in
  the config file, D222): on or off, when (in the installation's time zone), the tag, how many to keep, when the health
  check warns. Defaults: infrastructure every day at 01:00, application every Sunday at 02:00; both on.
* **Infrastructure**: on its schedule and on demand (`.\eax backup <tag>` or Back up now). The operations helper runs
  it; people keep working.
* **Application**: on demand (Back up every model now). A **model backup file** (`.eaxbackup.zip`) holds the deep model
  package (metamodel, content, history), the model as an Excel workbook, and what is needed to put the model back over
  itself. Model Admins back up their own model on its **Backups** tab. Documents and diagrams join them in phase 13.
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
| `eax restore-app [run\|tag\|latest] [--yes]` | Every model of an application backup put back over itself; models no longer there made again; newer ones left as they are (the api container must run) |
| `eax maintenance on\|off` | Shows the maintenance page to everyone (or stops showing it) |
| `eax restore-log <id>` | A restore's whole log |
| `eax delete-backup <name>` | Deletes an infrastructure backup (unpin it first) |
| `eax delete-restore <id>` | Forgets a finished restore and its log |
| `eax app-backup [tag]` | Backs up every model now (an application backup) |
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

## Moving to a server

Run `./eax.sh init server` on the server, set the host name, and certificate folder in
`eaexplorer.env`, replace every `change-me` value with your own passwords (the helper does not generate
them; the development password `P^55w0rd1234&` is refused on a server), start once, then restore a backup taken on the laptop. Deployment scripts for every
kind arrive in build phase 36.
