# Phase 13.5 — A console app: an interactive session with EA Explorer (requested, for later)

**Accepted and closed by the owner, 8 Nov 2026 (D337).**

Status: **built 8 Nov 2026** (0.15.1, D330) as `eax console`; to test: the checks below. The full description is in [command-line-and-console.md](command-line-and-console.md).

## The ask
A console (command-line) app that opens an **interactive session** with EA Explorer (eax): sign in once, then work
with models, projects and the repository by typing commands, without the web screens.

## Questions to settle when it is built
- What it talks to: the same REST API as the web (signed in through Keycloak, with the person's own roles), so it can
  do nothing the person could not do on screen.
- Sign-in: a device-code or browser sign-in, the token kept for the session (and refreshed); a service account for
  scripts.
- The session: a prompt with history and tab completion (model, entity type, entity, project and document names);
  a "current model" and "current project" like the last-model and last-project switchers.
- What it covers first: listing and finding (models, entity types, entities, projects, documents), reading an entity
  or document, changes (create, update, relate), imports and exports, check-out and check-in of documents, repository
  tags, background tasks (follow one, download its file), admin (users, backups, health).
- Plain language or commands: typed commands only, or also questions in plain language (through the MCP server EA
  Explorer already has)?
- Output: tables on screen, or JSON/CSV for scripts (--json); a script mode that runs a file of commands.
- How it is delivered: a Python package (pip install eax-console) and/or a single binary for Windows, macOS, Linux;
  the `eax` name is already the laptop's start-up script, so a different command name (eax-console, eaxc).
- Fits with 13.3 (parts turned off are not offered in the console either).

## What was decided and built (owner, 8 Nov 2026, D330)

The owner's answers changed the ask: the console is mainly for **getting a system that is down back up, by a person
who need not be technical**, so it is part of the `eax` command (`eax console`), not a separate tool:

- **A numbered menu** (no automatic check first): status, start, restart, stop, problems and logs, back up, restore
  (guided), reset a password, users and roles, settings and switches, background tasks and job servers, health and
  data quality with the audit trail, the maintenance page, a diagnostics file, and a prompt for every eax command.
- **Admin and operations only** (no model content: that stays in the screens and the MCP server).
- **On the machine, no password** (being on the machine is the trust); YES typed before anything that changes or
  replaces data; what is done is logged (work/logs/console-<date>.log, the config history, the audit trail).
- **Passwords**: a person's sign-in (temporary), Keycloak's administrator (with a bootstrap fallback when the stored one
  no longer works), break-glass, and the databases' logins; the other secrets with phase 36.
- **Two modes**: on the machine (runs in the operations helper; what needs the machine is handed back to eax), and
  `--server https://host` against a running installation through its API, signed in with Keycloak's device sign-in
  (client `eax-console`) and the person's own roles.
- **Later, phase 36**: the console on a remote machine whose API is down (SSH or an agent), and on an Azure or AWS
  cluster (todo.md, Productionising stories).

## Checks

1. `.\eax console` with everything running: the menu shows; 1 lists every service with OK.
2. Stop the API (`docker stop` its container), then 1 and 5: the API is shown as stopped with its last lines; 3 › api
   starts it again.
3. 4 then anything but YES: nothing stops; 4 then YES: everything stops and the basic menu shows; its 1 starts again.
4. 6 › Infrastructure with a tag: a backup is made; 7 › List the backups shows it.
5. 8 › A person's sign-in: find a user, make a password: signing in asks them to choose their own.
6. 8 › Break-glass: a new password is shown and the API restarts; break-glass sign-in works with it, not the old one.
7. 8 › A service password (EA Explorer's own login): it changes, everything starts again and works.
8. 9: list everyone with their roles; give a role and take it away.
9. 10 › Projects off: the screens follow (13.3); 10 › Optional services: switch draw.io off and on.
10. 11: the waiting and running tasks and the job queue; 12: every service's health; the audit trail shows the
    console's changes as "console".
11. 13 on: everyone sees the maintenance page; 13 off again.
12. c: `services` runs; an empty line returns to the menu.
13. From another computer: `.\eax console --server https://<host> --insecure`: the code sign-in works and the menu
    answers with your roles.

