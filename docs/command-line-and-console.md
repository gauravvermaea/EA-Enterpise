# The command line and the console

EA Explorer is installed, started, backed up and repaired with one command, **eax**, run in the main folder of the
installation:

| Computer | How to run it | Example |
|---|---|---|
| Windows | `.\eax <command>` (PowerShell; `eax.cmd` starts `eax.ps1`) | `.\eax up` |
| Linux, macOS | `./eax.sh <command>` | `./eax.sh up` |

Both do the same; this page writes `eax` for either.

**Help.** `eax help` lists every command by group with one line each; `eax help <command>` (or `eax <command> --help`)
shows one command in full with its options and examples; `eax help --all` shows every command in full. All forms
(`eax.ps1`/`eax.cmd`, `eax.sh`, `eaxpy`) print the same help from one file, `eaxcli/help.txt` (D331): change the help
there, and `tests/test_eax_help.py` checks that every command each script accepts is in it.

**All the documentation, with examples: `eax document`.** It asks whether to show it in the console or as a web page
(`--console` or `--web` skips the question):
- **Web page:** one file, `work/docs/eax-commands.html`, opened in your browser. It needs no server and loads
  nothing from outside: every command in full with its options and examples, grouped as in the help, with a contents
  list, a search box, links to each command, the commands that delete data marked, the *Starting and stopping* table
  below and a short part on the console. Light or dark, as your computer is set. It is made from `eaxcli/help.txt`
  each time (the page `eaxcli/document.html` with the help copied in), so it always says what `eax help` says.
- **Console:** a numbered menu of the groups. Choose a number to see that group's commands in full with examples, a
  page at a time (Enter for more, q to stop); `s` searches by a word; `q` quits.

**The Python version (phase 13.9, D331).** The same commands also exist as one Python program for every system:

| Computer | How to run it |
|---|---|
| Windows | `.\eaxpy <command>` |
| Linux, macOS | `./eaxpy.sh <command>` |

- **First run:** it fetches uv into `work/tools`, and uv fetches the Python it needs there too. Nothing is installed
  elsewhere, and `cleanup` keeps that folder.
- **Without internet:** put uv into `work/tools`, or set `EAX_UV` to a uv program.
- **Side by side:** `eax` and `eaxpy` stay side by side, and do the same, until the switch is made.

Most commands are for people who look after the installation. For anyone else, **`eax console`** is the place to
start when something is wrong. It is a numbered menu that says what to do in plain words (see
[The console](#the-console)).

## Contents

- [The groups, the menu and colours](#the-groups-the-menu-and-colours): eax menu, did you mean, --no-color
- [Starting and stopping](#starting-and-stopping): up (run), stop (down), restart, status
- Help and documentation: help, document (above)
- [Where things live](#where-things-live)
- [Getting started](#getting-started): init, check, up, run
- [Finding problems](#finding-problems): status, logs, diag, debug
- [Everyday use](#everyday-use): url, logins, trust, services, service, servers, maintenance
- [Backups and restores](#backups-and-restores)
- [Updating to a new release](#updating-to-a-new-release): update, rollback
- [Starting again](#starting-again): cleanup, clean-run, clean-debug, clean-restart
- [The console](#the-console): the menu item by item, the command prompt, the console against another installation
- [What is recorded](#what-is-recorded)
- [Remote machines and the cloud (later)](#remote-machines-and-the-cloud-later)

## The groups, the menu and colours

(R2.10, R2.29, D636.) `eax help` lists the commands in these groups, each with one line:

| Group | Commands |
|---|---|
| Start and stop | up (run), stop (down), restart, cleanup, clean-restart, clean-run, maintenance |
| Status and logs | status, url, logins, logs, diag, footprint, databases, persist |
| Backups and restores | backup, backups, restore, restores, restore-log, delete-backup, delete-restore, stop-backup, app-backup, restore-model, restore-app, schedule |
| Updates | update, rollback, packs, import |
| Test | check, test |
| Settings and services | services, service, servers, standby, secrets, trust |
| Site and deploy | init, deploy, console |
| Developer | debug, clean-debug |
| Help and documentation | help, menu, document |

**`eax menu`**, or `eax` with no command in a terminal, opens a numbered menu: choose a group, then a command; each of
its options is asked for in turn (a choice by number, a flag by y or n, a value typed; Enter leaves an optional one
out); the whole command is shown (`Will run: ./eax.sh restore latest --yes`) and runs only when you answer y. Piped or
in a script, `eax` with no command still prints the help. eax.sh and eax.ps1 hand the menu to the Python program, which
runs the chosen command in the same form you typed.

**Did you mean**: a command that does not exist shows the nearest ones, for example
`ERROR: unknown command 'stauts'. Did you mean: status? Run ./eax.sh help, or ./eax.sh menu to pick one.`

**Colours**: in a terminal, `eax status` shows each container in its state's colour (green up, yellow starting, red
down, unhealthy, restarting or out of memory, grey a finished set-up step), and errors (red), warnings (yellow) and
headings (cyan) are coloured. `--no-color` anywhere on the line, or `NO_COLOR=1`, `EAX_NO_COLOR=1` or `CI=1`, turns
colour off; output sent to a file or to another program is always plain, and the logs never hold colour codes.

## Starting and stopping

| Command | What it does | Your data |
|---|---|---|
| `eax up` (or `eax run`) | Starts EA Explorer: the core first, the rest in the background (`--wait-all` waits for everything). | Kept from last time |
| `eax stop` (or `eax down`) | Stops EA Explorer: stops and removes the containers. Use it before shutting the computer down or to free memory. | **Kept**: databases, documents, settings, backups |
| `eax restart` | `stop`, then `up` (each with its own log). For when something is stuck. | Kept |
| `eax status` | Every container's state and health, and the disks. Changes nothing. | Kept |
| `eax cleanup --all` | Stops EA Explorer and **deletes** the work folder and the databases (asks you to type yes). | **Deleted** (the trusted certificate is kept) |
| `eax clean-restart` | Stops, **deletes everything** and starts fresh with the sample data. Does not ask. | **Deleted** |

To stop without losing anything, always use `eax stop`.

## Where things live

Everything local is in the **work** folder (never committed to git):

| Path | What it holds |
|---|---|
| `work/eaexplorer.env` | The config file: the deployment kind, addresses, passwords, service switches. Containers read it when they start. |
| `work/config-history/` | A dated copy of the config file before every change made by the screens, `eax service`, `eax servers` or the console. |
| `work/logs/` | One log per eax command (`eax-<date-time>-<command>.log`) and the console's log (`console-<date>.log`). |
| `work/backups/infrastructure/` | Infrastructure backups (every database, document files, certificate, reports' home, import and export folders, config file). |
| `work/backups/application/` | Application backups (every model, one file each). |
| `work/backups/restores/` | Each restore's status and log. |
| `work/data/tls/` | The local certificate (laptop). Kept by `cleanup` unless asked. |
| `work/proxy/maintenance` | While this file exists, everyone sees the maintenance page. |

## Getting started

### `eax deploy [--console|--web] [--kind K] [--plan] [--yes]`
The guided deployment (phase 36, D498, D500): it asks **console or web page** first, then where: this **laptop**, a
**server** (here, or another one over SSH; Docker is installed if missing), or **AWS**, **Azure** or **DigitalOcean**
(the machine created from your credentials, or one you have). It makes the config file with every password
generated, starts EA Explorer, checks it is healthy and shows the address and the first sign-in. `--plan` shows every
command and runs nothing; a failed step asks Retry, Back or Quit. Not installed yet? The installer (`eax-deploy.cmd`
or `eax-deploy.sh`) downloads the version you choose from the repository link, then runs this. Every step in detail:
[deployment.md](deployment.md).

### `eax secrets [show|push|pull] [--to|--from provider:name]`
Keeps the passwords in a key vault as well (D504): `file:<path>`, `aws:<secret name>` (Secrets Manager) or
`azure:<vault name>` (Key Vault). `push` stores the config file's values there; `pull` puts the vault's values back
into the config file (a dated copy first, in work/config-history). See [deployment.md](deployment.md#4-passwords-from-a-key-vault-d504).

### `eax init [laptop|server]`
Creates `work/eaexplorer.env` from the template for the kind of installation (laptop if not given), and the work
folders. Nothing is generated:
- on a **laptop** every password is the same known one (`eax logins` prints them);
- on a **server**, replace every `change-me` value before the first `eax up`.

It refuses to overwrite an existing config file.

### `eax check`
Checks that Docker is running and that the config file and the compose files are valid. It starts nothing.

### `eax up [service...] [--wait-all]` and `eax run`
Builds EA Explorer's images, pulls the others, and starts everything in two tiers:
1. **The core:** sign-in (Keycloak), the database, the API and the screens. You can sign in when it says *ready*.
2. **The rest, in the background:** Reports, Documents, draw.io and the sample data.

`--wait-all` starts everything and waits until all of it is up. Naming services starts only those and what they
depend on; for example, `eax up api proxy` starts the database, the API and the web server only. `run` is the
everyday start and is the same as `up`. Running `up` on a running installation is an upgrade: everyone sees the
maintenance page until it has finished.

**Nothing to prepare by hand (D584).** A full `up` (and so `run`, `restart`, `debug`, `clean-run`, `clean-restart`)
first runs the pack step, `eax packs auto`: what is new or changed in the pack source folders is copied into
library/industry-packs (the "complete set" zips opened, the same file kept once); it is quick when nothing changed and
says one line when there is no source folder. The sources: `eax packs source <folder...>` (kept in persist/), else
`EAX_PACKS_SOURCE` in the config, else the default folders. As it starts it then loads the packs into Documents (the
start-up status shows *Industry packs loading n of N*), the documentation into the library, sign-in and Reports set-up,
the sample data and the persist/ settings, and builds the test runner in the background (about 1.5 GB). `eax test`
prepares the runner itself every time, so `eax packs collect` is optional. Testing is two choices (D592): `eax test` (smoke)
or `eax test full`; `eax test failed [run] [--warnings]` repeats only the checks that failed (D605); `eax test clean`
deletes the test data (D593).

## Finding problems

| Command | What it does |
|---|---|
| `eax status` | Every container with its state and health (stopped ones too), then the disks: Docker's, the work and backups folders, this computer's drive (size, used, free). |
| `eax logs [service]` | Follows the logs of every container, or of one (`eax logs api`). Ctrl+C stops following. |
| `eax diag` | Saves a diagnostics report into this run's log: Docker versions, memory and disk, every container's state and last 300 log lines, and the compose configuration with the passwords masked. Send that log when asking for help. |
| `eax debug [service...]` | Like `up`, but it does not stop on a failure. It saves a diagnostics report, then records every container's output to `work/logs/containers-<date-time>.log` until Ctrl+C. The containers keep running. |

## Everyday use

| Command | What it does |
|---|---|
| `eax url` | Prints the addresses to open (and, on a laptop, the logins). |
| `eax logins` | Prints every user name and password (laptop only). |
| `eax trust [--remove]` | Windows: adds the local certificate to the trusted root certificates, so the browser stops warning about `https://localhost`. `--remove` takes it out again. |
| `eax services` | The optional services (reports, documents, drawio, mcp, change_log, backups, library, views): whether each is on in the config file, and its containers' state. |
| `eax service <name> on\|off` | Switches an optional service on or off. It keeps a dated copy of the config file, writes the switch, then starts or stops the service's containers. Also in System admin › System settings › Services. |
| `eax servers [n]` | How many API and job servers run. With n (1 to 16), it writes `EAX_API_SERVERS` (a dated copy first) and adds or removes servers without a restart. |
| `eax maintenance on\|off` | Shows the maintenance page to everyone, or stops showing it. Restores and upgrades switch it themselves. |

**Projects, Repository and References** (phase 13.3, D329) are switched on or off by a Super Admin in System admin ›
System settings, or in the console (menu item 10). They are not eax commands because they are application settings:
- they apply at once, with no restart;
- switching one off keeps its data;
- switching Projects off switches the Repository and References off too.

## Backups and restores

There are two kinds of backup:

- An **infrastructure backup** holds every database (the library's and the views' too, from their own servers when
  they have them), the logins and roles, the document files, the certificate, the reports' home, the import and export
  folders, the config file, and the release and image versions. It is what you need to rebuild the machine; restored on
  a new server, it makes the logins and roles first (D410).
- An **application backup** holds every model, one file each, every project with its documents, and the organisation
  part: the organisation's own views and project templates, skills, the board and the enterprise library (D410).

| Command | What it does |
|---|---|
| `eax backup [tag]` | An infrastructure backup now, with a tag to find it by. |
| `eax app-backup [tag]` | An application backup now (needs the API running). |
| `eax import [source\|--all] [--as user]` | Takes the files other systems dropped in their delivery folders (phase 34): each becomes a delivery, previewed and waiting for review on the model's Deliveries tab. Without a source: lists the sources, their folders and what waits. See [import-formats.md](import-formats.md). |
| `eax backups [words]` | Lists every backup (infrastructure ones numbered); with words, only those whose tag, name or maker has them. |
| `eax restore [name\|tag\|latest] [--what ...] [--yes]` | Restores an infrastructure backup (see the list of what it can put back below). Without a name it lists the backups to choose from, asks what to restore, and asks you to type RESTORE. A backup of the current state is taken first, and nothing live changes until everything is restored cleanly. It works when the screens are down. |
| `eax restore-app [run\|tag\|latest] [--yes]` | Puts every model of an application backup back over itself (each model is backed up first). Models no longer there are made again; newer models stay as they are. |
| `eax restore-model` | Choose an application backup and one model in it, then restore that model as a new model or over itself. |
| `eax restores` | Every restore with its status. |
| `eax restore-log <id>` | One restore's whole log. |
| `eax stop-backup` | Stops the backups that are running; the partial backup is deleted. A restore cannot be stopped. |
| `eax delete-backup <name>` | Deletes an infrastructure backup (unpin it first if it is pinned). |
| `eax delete-restore <id>` | Forgets a finished restore and its log. |

What `eax restore --what` can put back:

| `--what` | What is put back |
|---|---|
| `full` | Everything |
| `app` | The config file |
| `app+data` | The config file, the repository, library, views and document databases, the document files, and the import and export folders |
| `db` | Every database |
| `files` | The document files (with Documents' database), the certificate, the reports' home, and the import and export folders |

A **project backup** (one architecture project, with its documents and models) is made and restored on the project's
page or in Project admin. One made by an older EA Explorer is upgraded as it is restored (D328).

## Updating to a new release

Phase 36 (D417, D511): see [phase-36-updates.md](phase-36-updates.md) and [release-process.md](release-process.md).

| Command | What it does |
|---|---|
| `eax update` | Guided: the installed version, the channels (Prod; RC and Latest once enabled), the versions above the installed one with their notes; which one, now or at a time, and YES. A pinned full backup (code, databases, files, config) first, then the maintenance page while each release on the way is built and checked. The update runs in its own updater container; this window follows its log until EA Explorer restarts. |
| `eax update --status` | The installed version, the repository link, the channels, the update running or waiting, the schedule and the history. |
| `eax update --channel prod --to 0.20.0 [--at 22:00] [--yes]` | Not guided. `--at` schedules it (signed-in people see a banner beforehand). |
| `eax update --url <link>` | Sets the repository link (EAX_UPDATE_GIT_URL). |
| `eax update --retry` | A failed update: the failed step again, then the rest. |
| `eax rollback [--yes]` | Back to the version before the last update: its code and its pre-update backup put back (work since is lost; the current state is backed up first). |

The same on System admin › Updates (IT Admins and Super Admins).

## Starting again

These commands can also be run from System admin › Command centre (Super Admins, behind a strong confirm and a
backup first; see [Command centre](#command-centre-eax-commands-from-a-web-page-d554)).

| Command | What it does |
|---|---|
| `eax cleanup [--all] [--yes] [--certificate]` | Stops the containers and empties the work folder: the config file, the logs and the data folders, backups included. `--all` also deletes the Docker volumes, so the databases and documents start empty. The local certificate is kept unless `--certificate` is given. It asks you to type yes unless `--yes` is given. |
| `eax clean-run [laptop\|server]` | From scratch in one step: `cleanup --all --yes`, `init`, `up`. It does not ask. |
| `eax clean-debug [laptop\|server]` | The same, ending with `debug`. |
| `eax clean-restart [laptop\|server]` | For testing a new version: `down`, then `clean-run`. Rebuilds the images and starts with empty databases. |

## Command centre: eax commands from a web page (D554)

**System admin › Command centre**, for **IT Admins and Super Admins**, runs the eax commands from the browser. It has
three tabs:

- **Commands**: every command, grouped as in `eax help` (it is read from `eaxcli/help.txt`, so it never drifts). Choose
  one: a short form explains what it does and what it keeps or deletes, asks for each option, shows the exact command
  line (for example `eax restore latest --what db`) and runs it after you confirm. The output streams live; `logs`,
  `debug`, `status`, `test` and other read-only commands can be stopped halfway.
  - **Stops or restarts EA Explorer** (amber: `stop`, `restart`, `up`, `update`, `rollback`, `restore`, `restore-app`,
    `maintenance`, `standby`): the page says so; it keeps asking every few seconds and carries on when EA Explorer is
    back. After `stop`, start it again on the machine with `eax up`.
  - **Deletes everything** (red: `cleanup`, `clean-run`, `clean-restart`, `clean-debug`): **Super Admins only**. A red
    warning lists what goes (every database, the document files, the config file, the logs and every backup in
    work/backups); you type the installation's name (`EAX_INSTALLATION_NAME`, else `EAX_HOSTNAME`, else the folder's
    name) and tick "I understand". A fresh infrastructure backup is taken first and copied to `persist/safety-backups/` beside
    the work folder, which no cleanup deletes.
  - **Runs on the machine itself** (grey: `init`, `check`, `trust`, `deploy`, `secrets`, `document`): shown with why and
    the exact command to type there, with a Copy button.
- **Console**: a terminal in the browser. Type eax commands as on the machine (`eax status`, `backup nightly`,
  `help restore`; the `eax` is optional) with their real output and questions; `console` opens `eax console`'s
  numbered menu. **Only eax commands run, never a shell**: anything else, or a line with `; | & $ \` < >`, is refused
  with a short message. The delete-everything commands ask for the installation's name and "I understand" here too.
- **History**: every run and console session (who, when, the command, the exit code), with its output or the session's
  transcript and every line typed (refused ones too).

How it runs: the operations helper starts a short-lived container of its own image for each command (the installation
folder and the Docker socket mounted, like the updater), outside Compose, so a command that stops or empties the stack
still finishes. In it, `eaxcli/cmdrun.py` checks the command again and runs it through `eaxpy` (the same code as typing
it); its record is in `work/commands/<run>/` (status.json, output.log). The Console runs `eaxcli/webconsole.py` the same
way, in the terminal of the container terminals (D214). Every run and session is in the audit trail (`command.run`,
`command.console.open`, `command.end` with the exit code).

The same Commands, Console and History tabs are on **`eax deploy`'s web page** (see [deployment.md](deployment.md)): there
EA Explorer may not be up, so the commands run straight on the machine through eaxcli, or on the server the wizard set
up over its SSH connection. Both use one module, `eaxcli/commands.py`: the catalogue, the checks and the strong confirm.

## Schedules: a cron in the platform (D559)

System admin > Command centre > **Schedules** and `eax schedule` run eax commands by themselves, in the installation's
time zone (`EAX_TIMEZONE`): every night at a time, every week on a day, every hour, once, or a cron expression
(`minute hour day month weekday`). The operations helper looks every 30 seconds and starts what is due in the Command
centre's runner container, so a schedule that runs `clean-restart` still finishes while the stack goes down and comes
back. A run missed while the machine was off runs once if found within the hour (later: skipped and recorded); a run
due while another command runs waits up to 30 minutes, then is skipped with a note. Every run is in the History.

A command that deletes everything (`clean-restart`, `clean-run`, `cleanup`) can be scheduled by Super Admins only, with
the strong confirm given once, when the schedule is made. By default it takes a safety backup first into
`persist/safety-backups/`, keeping that schedule's newest 3. **Demo reset every night** (a button, or
`eax schedule demo-reset --confirm <installation name>`) schedules `eax clean-restart laptop` at 02:00 with no backup
first and a banner telling everyone. The schedules are kept in `persist/schedules.json` (see "Settings that survive
resets").

```
eax schedule list
eax schedule add "Nightly backup" --at 01:30 -- backup nightly
eax schedule add "Weekly smoke test" --weekly 1 --at 06:00 -- test --smoke
eax schedule demo-reset --at 02:00 --confirm demo-laptop
eax schedule off a1b2c3
eax schedule run a1b2c3
```

`eax schedule` is not offered on the Commands tab or in the Console (it runs on the machine): use the Schedules tab.

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

## The console

`eax console` (phase 13.5, D330) is for **getting a system that is down back up, by someone who need not be
technical**:
- a numbered menu, in plain words;
- every step says what it will do;
- anything that changes or replaces data asks you to type **YES** (in capitals) first. Anything else stops.

**No sign-in on the machine.** Run on the machine where EA Explorer is installed, the console asks for no password:
being able to run commands on that machine is the trust, as for every eax command. What it does is recorded (see
[What is recorded](#what-is-recorded)).

**How it runs.** The console runs inside the operations helper, a small container that reaches Docker and the work
folder. eax starts that container first.
- If it cannot start (Docker is not running, or nothing is set up yet), a **basic menu** appears instead: Start
  everything, Save a diagnostics file, Command prompt, Quit.
- After *Stop everything*, the basic menu is shown until you choose to start again.

### The menu

```
EA Explorer console  (laptop, 0.15.1)

 1  Status: what is running, what is not
 2  Start everything
 3  Restart everything / one service
 4  Stop everything
 5  Show problems and recent errors (logs)
 6  Back up now (infrastructure / application)
 7  Restore a backup (guided)
 8  Reset a password (a person, Keycloak admin, break-glass, service passwords)
 9  Users and roles
10  Settings and switches (Projects, Repository, References, optional services)
11  Background tasks and job servers
12  Health and data quality, audit trail
13  Maintenance mode on / off
14  Save a diagnostics file for support
 c  Command prompt (every eax command)
 q  Quit
```

In every list, type a number to choose, or **b** to go back.

**1 Status.** Every service with OK, `--` (stopped) or `!!` (unhealthy), and what Docker says. It ends with a line
saying either that everything is running or what is not and what to choose next. It also warns:
- when the maintenance page is on;
- when a disk is almost full.

**2 Start everything.** The same as `eax up`: the core first, the rest in the background. When it finishes, the
console comes back.

**3 Restart everything / one service.** Choose *Everything* (one service after the other, the database first) or one
service. Anything that had stopped is started too. People are signed out of what restarts for a minute or two.

**4 Stop everything.** The same as `eax down`, after YES. The data is kept. Nobody can use EA Explorer until it is
started again (2).

**5 Show problems and recent errors.** Each service that is stopped, unhealthy, or whose set-up step failed, with the
error lines from its recent log (or its last lines when there are none). When everything is healthy, you can still
read any service's last 40 lines. If a service keeps stopping, choose 14 and send the file.

**6 Back up now.**
- *Infrastructure* (every database, the documents, the certificate and the config file) starts the database and the
  backup service if needed.
- *Application* (every model) runs in the API.

Give a tag to find the backup by, or press Enter for *on-demand*.

**7 Restore a backup (guided).**
- *Infrastructure:* the same guided restore as `eax restore`. Choose the backup from a numbered list, then what to
  put back (full, the config file, config and data, the databases, or the files), then type RESTORE. The current
  state is backed up first, everyone is told, and the maintenance page is shown until it is done.
- *Every model from an application backup*, or *one model*.
- *List the backups*, and *the restores so far*.

**8 Reset a password.** Each reset shows the new password **once**. Tell it to the person in person or by phone, not
by email. For a new password, choose *Make one for me* (24 letters and digits; recommended) or type one: at least
12 characters, with no spaces, quotes, `$`, `` ` `` or `\`.

| Choice | What happens |
|---|---|
| A person's sign-in | Find the person by part of their name or email. They get a **temporary** password and choose their own at their next sign-in. A disabled person is enabled again. Done in Keycloak with its own admin tool. |
| Keycloak's administrator | Sets the password of Keycloak's administrator and writes it into the config file (a dated copy first). If the password in the config file no longer works, a temporary administrator is made with Keycloak's own bootstrap command, used for the reset, then removed. |
| The break-glass account | The account that signs in when Keycloak is down. The new password is written into the config file, then the API is started again to take it. Everyone signed in with break-glass is signed out. |
| A service password | The databases' logins: the administrator, EA Explorer's own, the reports' read-only one, the installer's, Keycloak's, Reports' and Documents'. Choose one, or all at once. New passwords are made, set in PostgreSQL and written into the config file (a dated copy first). Then every service is started again to use them (a few minutes). The other secrets (sign-in client secrets, Reports' and Documents' own administrators, the document queue) change with phase 36, which also brings a key vault. |

**9 Users and roles.** People and their global roles are kept in Keycloak. The console changes them there, with
Keycloak's own admin tool.
- *List everyone with their roles.*
- *Give someone a role* and *Take a role away* (it applies at their next sign-in).
- *Disable or enable a person.*
- *Add a person* (then give them a temporary password with 8 and roles here).

A person's roles on a model stay on that model's People tab.

**10 Settings and switches.**
- *Projects, Repository, References and the system settings*:
  - the parts of EA Explorer in use (Projects off also switches the Repository and References off; their data is kept);
  - the largest upload, how long change log entries are kept, the session time-outs, the log level.

  Each setting is shown with its value and help; choose one to change it. These run in the API (start it first if it
  is down).
- *Optional services on or off*: reports, documents, draw.io, MCP, change log, backups, library, drawn views (views). This is the same as
  `eax service`, with a dated copy of the config file first.

**11 Background tasks and job servers.**
- *Background tasks*: everyone's tasks that are waiting or running, and the job queue. Cancel one queued task, or
  every queued one. The people who asked see them as cancelled. A running task cannot be stopped from here: it
  finishes, or restart the API.
- *API and job servers*: how many run, and set how many should (1 to 16), as `eax servers`.

**12 Health and data quality, audit trail.**
- *Every service's health now*: the same checks as System admin › Health.
- *Measure the data quality of every model now*: queued in the background.
- *The audit trail*: the last 30 things done, by whom and from where.

**13 Maintenance mode on / off.** Shows or hides the maintenance page for everyone. While a restore runs, it is left
to the restore.

**14 Save a diagnostics file for support.** The same as `eax diag`. Its log file is the one to send.

**c Command prompt.** Type any eax command without `eax` in front (for example `logs api`, `services`,
`backups karoo`). An empty line or `back` returns to the menu.

### The console against another installation

```
eax console --server https://ea.example.org [--realm eaexplorer] [--insecure]
```

This works on an installation that is **running**, through its API, from any computer with EA Explorer's folder and
Docker:
- **Sign-in:** you sign in with Keycloak's device sign-in. The console shows a web address and a code; open it in a
  browser, sign in and check the code.
- **Roles:** everything is done with **your own roles** (IT Admin or Super Admin for most of it).
- **Certificate:** `--insecure` accepts a laptop's own certificate.

Its menu:
- status (every service's health);
- restart everything or one service;
- what is not running, with its last lines;
- back up now;
- restore an infrastructure backup;
- users and roles (read only);
- settings and switches;
- your background tasks and the job servers;
- data quality now and the audit trail.

Passwords, users' roles, starting and stopping are done **on the machine** (`eax console` there), because they must
work when the API cannot.

The device sign-in uses the Keycloak client `eax-console`. A new installation gets it with its realm; an installation
from before 0.15.1 gets it with a clean install, or by adding the client in Keycloak's screens (public, *OAuth 2.0
Device Authorization Grant* on, with an audience mapper for `eax-api`).

## What is recorded

- Every eax command writes its full output to `work/logs/eax-<date-time>-<command>.log`.
- The console writes what it did to `work/logs/console-<date>.log`. Passwords are never written there.
- Every change to the config file leaves a dated copy in `work/config-history`.
- Settings, cancelled tasks and other changes made in the application are in the audit trail as
  *console (on the machine)*.
- Keycloak keeps its own record of password and role changes.

## Remote machines and the cloud

Deploying to a server over SSH and to AWS, Azure and DigitalOcean is `eax deploy` (phase 36, [deployment.md](deployment.md)):
each cloud machine runs our Docker stack, so the console, logs, backups and restores work there as on any server
(sign in to it over SSH and run `./eax.sh console`, or use `eax console --server https://<address>` from here).
Passwords can be kept in a key vault (`eax secrets`). Several hosts and scaling out: 36.3.

`eax databases` lists every database EA Explorer uses, where it lives and whether it answers (R2.50, D611; docs/databases.md).

New on 13 Nov 2026: `eax persist` (R2.26), `eax logs backup | clean` (R2.30), `eax footprint` (R2.22), `eax test ui-review` (R2.12), `eax databases copy tests | operations` (R2.27, R2.28); `eax status` starts with the release and build (R2.47).
