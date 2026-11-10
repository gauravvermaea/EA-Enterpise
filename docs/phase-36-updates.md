# Phase 36 — Updating to a new release (design agreed, to build)

Status: **design agreed with the owner, 10 Nov 2026 (D417); built 10 Nov 2026 in 0.19.0 (D510 to D516), see As built.** Part of phase 36 (deployment kinds, D416).

## What it does
Once EA Explorer is installed, an admin moves it to a newer release **from the web console** (System admin › Updates)
or **from the command line** (`eax update`, all four forms, D331), guided or not. The organisation decides when; nothing
updates by itself.

## Where releases come from
- **One setting: the git URL** of the EA Explorer repository (System admin › Updates, and `work/eaexplorer.env`). The
  repository is **public**: no credentials.
- **Built on the host**: an update fetches the chosen version and builds the images on the server, as `eax clean-restart`
  does today. No image registry.
- **Three channels** (branches and tags):

  | Channel | Branch | Versions offered | Default |
  |---|---|---|---|
  | **Prod** | `release` | tags `vX.Y.Z` | on |
  | **RC** | `rc` | tags `vX.Y.Z-rc.N` | greyed out until enabled |
  | **Latest** | `main` | each commit (date and short id) | greyed out until enabled |

  Choosing a channel lists its versions with their release notes (the release's notes file in the repository); the
  admin picks one.

## Rules
- **Forward only.** A version lower than the installed one is never offered (on Latest: an earlier commit). The installed
  version, its channel and commit are kept, with the history of every update (from, to, who, when, the backup taken,
  the result), on the host and in the database.
- **Everything is backed up first**: a full infrastructure backup (every database, every file set, the configuration,
  D410) plus the code as it is (the commit, and any local changes, kept in the backup). The backup is pinned.
- **Several releases behind**: if the installation is more than one release behind (e.g. three), the update goes
  **one release after another, in order**, each built, upgraded and checked before the next; one backup before the
  first step.
- **If a step fails** (build, database upgrade, or the health check after restart): **stop and ask**. The system stays
  on the maintenance page with the log; the admin chooses **Retry** or **Roll back**.
- **Roll back to the last working version**: puts back the backup taken before the update: code, databases, files and
  configuration exactly as they were. Work done since the update is lost, so the screen says how long ago the update
  was and takes a backup of the current state first (kept). After a rollback the failed version is marked in the
  history.
- **When**: now, or at a time the admin picks (e.g. tonight 22:00). Signed-in people see a banner beforehand; during the
  update everyone sees the maintenance page; afterwards a *What's new* note with the release notes.

## Who
**Super Admins and IT Admins** enable RC and Latest, run updates and roll back (web console). On the command line,
whoever runs `eax update` on the host.

## Command line
`eax update` (guided: shows the channels, versions and notes, asks to confirm), `eax update --channel prod --to v0.17.0
[--at 22:00]`, `eax update --status` (installed version, history), `eax update --retry`, `eax rollback` (to the last
working version). All four forms (D331).

## How it runs
The web console asks the ops service, which starts a short-lived **updater** container on the host (with access to
Docker and the installation folder) so the update survives the API and ops restarting. It writes progress to a log the
console and `eax update --status` show.

## Before the first release (owner, 10 Nov 2026)
The owner creates the `release` and `rc` branches and starts tagging versions before the first release, and gives
the git URL then (we give him the git commands; he runs git).

## Decided when built (D510)
The release notes are `releases/<version>.md` in the repository at the tag (an RC without its own file shows its
release's); Latest shows the one-line messages of the commits since the installed commit. See
[release-process.md](release-process.md).

## As built (10 Nov 2026, 0.19.0, D510 to D516)

**Where the code is**
- `eaxcli/releases.py`: the channels, version names and order, what a channel offers (git ls-remote and a small bare
  cache repository, work/updates/cache.git), the plan (one release at a time), the notes, a version's files
  (`export`, also for `eax deploy`, D498) and the supported-versions policy. Standard library and git only.
- `eaxcli/updater.py`: the updater. It runs in a short-lived **updater container** (the operations helper's image, which
  now carries git) with the Docker socket and the installation folder mounted at the same path as on the host, so
  Compose resolves the same folders; it is not part of the Compose project, so `up --remove-orphans` never stops it.
  It copies itself to work/updates/<id>/runner first.
- `services/ops/updates.py`: the helper starts the updater (on the default network for the repository, connected to
  the backend network to reach the helper and the API), lists versions through a `--rm` container (the helper itself
  has no internet), keeps the schedule, and serves `eax update` and `eax rollback`. The helper now mounts `eaxcli`
  and `services/api/version.toml` read-only.
- The API (`eax/updates.py`, `api/updates.py`): System admin › Updates relayed to the helper; the host's record copied
  into `core.update_history` (migration 0044); the banner and What's new; the administrators told. Job
  `eax.update_watch` every 5 minutes (and the daily support check).

**What it keeps** (work/updates on the host, first; the database has a copy): `installed.json` (version, channel,
commit, ref), `current.json` (the update running or waiting for a decision), `history.json`, `scheduled.json`,
`failed-versions.json`, and per update `<id>/update.log`, `request.json`, `code.tar.gz` + `files.txt` + `code.json`
(the code as it was: every file, local changes included, never work/, .git or library/templates).

**An update**: a pinned infrastructure backup through the helper (every database, file set and the config file) with
the code archive copied into it; the maintenance page; for each release: its files (`git fetch` of the tag and
`git checkout --force --detach`, or for a folder that is not a git checkout the version's files written over it, files
it no longer has removed), `docker compose build`, `up -d --remove-orphans` (the API upgrades the databases as it
starts), then the check: the API's heartbeat answers that version with the database at the same version (20 minutes,
`EAX_UPDATE_HEALTH_MINUTES`). Then the maintenance page off and the history written. Local changes to the code are kept
in the backup, not carried over.

**A failed step** stops with the maintenance page on and the log; **Retry** runs that step again and carries on;
**Roll back** keeps the code as it is now (before-rollback), puts the kept code back (the commit checked out, every
file as it was, newer files removed), builds and starts it, then restores the pre-update backup in full through the
helper (which backs up the current state first, pinned), checks the old version answers, and marks the failed version
(offered afterwards as "failed here before"). A rollback is also possible after a successful update (the last one).

**When**: now or at a time (`--at 22:00` or a date and time; the helper starts it); a banner for everyone signed in
beforehand; What's new once for each person afterwards (14 days). **Who**: `system.operate` (IT Admins, Super Admins).

**Commands** (all four forms, help in eaxcli/help.txt): `eax update` (guided), `--status`, `--retry`, `--channel`,
`--to`, `--at`, `--url`, `--yes`; `eax rollback [--yes]`. `eax update` runs in the helper (`compose exec ops`); it
follows the updater's log until EA Explorer restarts (the update itself carries on).

**Sample data** (laptop): an update that succeeded, one rolled back (an RC), one that did not start, one scheduled,
marked sample (never told to anyone).

**Not tested here**: a real `docker compose build` and `up` from the updater container on Docker Desktop and on Linux,
and a real public repository; the tests use a local bare repository and fakes for Compose, the helper and the API.

