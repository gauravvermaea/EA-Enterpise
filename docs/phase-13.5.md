# Phase 13.5 — A console app: an interactive session with EA Explorer (requested, for later)

Status: **requested for later** (owner, 8 Nov 2026). Not designed or built yet; discuss before building.

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
