# Build phase 8.4: backups and restores

Goal: everything can be put back. Pulled ahead of its place in the plan (owner, 6 Nov 2026); version **0.12.0**,
migration `0019_backups`. Decisions D74, D201, D216, D217, D222, D225 to D237. Documents and diagrams join the model backups when the document
management of phase 13 is built.

## Status: accepted and closed (6 Nov 2026)

## What phase 8.4 delivers

- **Infrastructure backups** (IT and Super Admins; ADM-005 to ADM-010, ADM-085, ADM-090, ADM-091):
  - One **tagged** folder per backup in `work/backups/infrastructure` (always there; mount a share at `work/backups` to keep
    them elsewhere, D226): every database on the server (pg_dump), the
    logins and roles, Mayan's document files, the site certificate, the config file, the release version with every
    image's name and digest, the compose files; a manifest and checksums.
  - **On a schedule** (default every day at 01:00 in the installation's time zone) and **on demand** (Administration >
    Backups > Back up now with a tag, or `eax backup <tag>`). People keep working (no lock).
  - **Restore** whole or in part: full, app (the config file), app+data (config, repository and document databases,
    document files), db (every database), files (documents and certificate); from the console or `eax restore <name>
    --what ...`, which works when the console cannot run. A backup of the current state is taken first and pinned; the
    installation is **read only** while restoring (every change refused with why, a banner on every screen); the
    services that use what is restored stop and start again; everyone signs in again. A backup from a newer version is
    refused for the databases; a partial restore warns that documents and their records may not match.
- **Application backups** (IT and Super Admins; ADM-086, ADM-087): every model as a **model backup file**
  (`.eaxbackup.zip`: the deep model package with metamodel, content and history, the model as an Excel workbook, and
  what is needed to put it back over itself), in one tagged folder; download any model's file; **restore** one as a
  new model (Model Creators and Super Admins; under its root metamodel when that matches, otherwise a root of its own;
  a draft) or over the model it came from; **upload** a file from another installation to restore it here.
- **Model backups** (ADM-089): the model page's **Backups** tab for its Model Admins: back up now with a note, the list
  (its own and its files in application backups), download, pin, restore as new or **over itself** after typing its
  name (the state now is kept first as a model backup and a tag; the backup becomes one commit of kind restore).
- **Schedules** (D222): Administration > Backups > **Schedules**, for IT and Super Admins: for each kind, on or off,
  when (every day at 01:00, weekdays, every Sunday, the 1st of the month, or any cron schedule, in the installation's
  time zone), the tag of the backups it makes, how many to keep, and (infrastructure) after how many hours without a
  backup the health check warns. Kept in the database (`core.backup_schedules`) and audited; **nothing about backups
  is in the config file**. Defaults: infrastructure every day at 01:00, application every Sunday at 02:00 (both on), keep 7, warn after 36
  hours. The job runner starts what is due every minute.
- **Kept**: the newest of each kind as set in the schedules (and the same number of each model's own); the oldest
  beyond that are removed after each backup; **pinned** backups always stay.
- **Restores** (D227, D228): each one runs on its own (the console only follows it); recorded with its whole log in
  `work/backups/restores/<id>`; **Administration > Restores** lists them with their status and log and deletes finished
  ones; a **lock page** on every screen while an infrastructure restore runs (through the proxy, so it works while the
  API is stopped); nothing live changes until everything has been restored cleanly (databases into `__restoring`
  copies, files beside the live ones, then swapped; put back on failure); restores can be **repeated** and first put
  right what an interrupted one left. Backups and restores can be **deleted by hand**.
- **Command line** (D227): `eax backup`, `eax backups`, `eax restore` (choose from a list), `eax restores`,
  `eax restore-log`, `eax delete-backup`, `eax delete-restore`, `eax app-backup`, `eax restore-model` (choose a backup
  and a model); see `docs/operations.md`.
- **Notifications, maintenance page, stop, search, whole application** (D229 to D233): everyone is told when a restore
  starts and ends; a restore brings everything down and the proxy shows a plain maintenance page (also during eax up and
  eax maintenance on); backups can be stopped; backups are searchable by tag; an application backup can be downloaded
  and restored whole (Download all, Restore all, eax restore-app).
- **Jobs**: every backup and restore of a model runs as a task (the top bar follows it); infrastructure backups and
  restores run in the operations helper (it keeps running while the API is stopped for a restore).
- **Audit**: backups, restores, pins, uploads and clean-ups are in the audit trail and the change log.
- **Upgrades**: an infrastructure backup, pinned, before every upgrade (ADM-064, built with phase 8.5).

## Demo

1. `.\eax clean-restart`. As an IT Admin: Administration > **Backups** > **Schedules**: infrastructure every day at
   01:00, keep 7; **Change...** application (on, every Sunday at 02:00) to keep 4. Then tag `before-demo` > **Back up now**. The top
   bar follows it; the backup is listed with 4 databases, documents and tls files, config and versions.
2. **Pin** it. `.\eax backups` lists it, pinned.
3. **Back up every model now** with the tag `end-of-quarter`; open it: one file per model with its counts; download
   Fynbos Life's and open `workbook.xlsx` inside it in Excel.
4. As `user_model_admin`: Fynbos Life > **Backups** > `before reorganising` > Back up now. Delete a few entities and
   commit. **Restore...** > Over Fynbos Life, type its name: the entities are back as one commit; the Tags tab has the
   state before; the Backups tab has a backup "before restoring the backup of ...".
5. As a Super Admin: restore Karoo Re's file from `end-of-quarter` **as a new model**: a draft with the same counts.
6. Administration > Backups > `before-demo` > **Restore...** > `files` > type RESTORE: the banner says read only, the
   log shows the documents service stopped, restored and started; sign in again.
7. With the console stopped (`docker compose stop api`): `.\eax restore <name> --what db`, then `.\eax up`.

## Checks

- `tests/sql/phase8_4_checks.sql`: the version, the tag kind `backup`, the two schedules and their rules.
- `pytest`: `tests/test_backups_infra.py` (the operations helper's backups and restores with Docker replaced: tags,
  code and config kept, retention with pinning, app+data restore in maintenance with services stopped and started and
  the config file back, refusing newer and unknown backups) and `tests/test_backups_app.py` (model files, listing,
  pinning, clean-up, paths kept inside the folder, uploads, routes and permissions).

## Notes

- Backups are not encrypted (owner's choice, D216): anyone who can read the backup folder or a downloaded file can read
  every model, and the config file's passwords.
- Backups live in files, never in the database, so restoring a database cannot lose the list of backups.
- `backup.sh` and `restore.sh` (the backup container) were tested against PostgreSQL: a database comes back with its
  owner, grants and settings (`pg_restore --create`), a damaged backup is refused by its checksums.
