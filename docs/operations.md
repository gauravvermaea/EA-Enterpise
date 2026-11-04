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
| List backups | `docker compose --env-file work/eaexplorer.env exec backup list.sh` | same |

## The work folder and logs

`work/` holds everything local and is never committed: `work/eaexplorer.env` (the config),
`work/logs` (one log per command, kept 14 days; `containers-*.log` from `debug`) and, on a laptop,
`work/data` (backups, imports, exports, tls). Database and document data live in Docker volumes,
which `cleanup --all` deletes. Passwords and secrets are masked in diagnostics and container logs.

## Backups

The backup container runs `backup.sh` on `EAX_BACKUP_SCHEDULE` (cron format) and keeps
`EAX_BACKUP_KEEP_DAILY` days. Each backup is a folder in `EAX_BACKUP_DIR`:

```
20261103T020000Z/
  eaexplorer.dump  keycloak.dump  superset.dump  mayan.dump   (pg_dump custom format)
  globals.sql                                                  (logins and roles)
  mayan-files.tar.gz                                           (Mayan's document files)
  manifest.json  SHA256SUMS
```

## Restore

1. Stop the containers that use the databases:
   `docker compose --env-file work/eaexplorer.env stop api reports dms keycloak`
2. Restore: `.\eax restore 20261103T020000Z` (checksums are verified first).
3. Mayan's files: extract `mayan-files.tar.gz` into the Mayan volume or `EAX_DOCS_DIR`.
4. Start again: `.\eax up`.

To test a backup without touching live data: `.\eax restore 20261103T020000Z --scratch`
restores into `*_restore_test` databases.

## Moving to a server

Run `./eax.sh init server` on the server, set the host name, and certificate folder in
`eaexplorer.env`, replace every `change-me` value with your own passwords (the helper does not generate
them; the development password `P^55w0rd1234&` is refused on a server), start once, then restore a backup taken on the laptop. Deployment scripts for every
kind arrive in build phase 36.
