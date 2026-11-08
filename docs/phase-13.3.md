# Phase 13.3 — Turn Projects, Repository and References on or off (requested, for later)

**Accepted and closed by the owner, 8 Nov 2026 (D337).**

Status: **built 8 Nov 2026** (0.15.1, D329); to test: the checks below.

## The ask
An installation-wide switch to **enable or disable** each of:
- **Projects** (architecture projects, project admin, the project library and templates),
- **Repository** (the Enterprise Repository, organisation and project level),
- **References** (the organisation's reference library and project references),

so that an organisation that needs **only the metamodel** (models, metamodels, data quality, reports) can run EA
Explorer as a lighter application.

## Questions to settle when it is built
- Who switches them (Super Admin, System admin › Settings) and whether a restart is needed.
- Turned off: hidden from the menus and their API refused, with the data kept (turning back on shows it again)?
- Lighter at run time too: are services not needed then left out (Documents/Mayan, the project database, background
  repository builds) and the start-up sample projects skipped?
- Dependencies: Repository and References lean on Projects for project-level parts; turning Projects off turns their
  project parts off.
- Install choice: offered at installation as well as later in settings?

## What was decided and built (owner, 8 Nov 2026, D329)

- A **Super Admin** switches them in **System admin › System settings** (three switches: Projects, Repository,
  References); also in the console (`eax console`, 10). They apply at once, no restart.
- Off: the part's **menus, start-page tile, pages and API are gone** (the API answers 404 saying it is switched off;
  a page opened by its address says so and points to the setting); its MCP tools answer that it is off; its
  background work waits. **The data is kept** and comes back when it is switched on.
- **Projects off switches the Repository and References off too** (they show what projects hold); either of them cannot
  be switched on while Projects is off. Repository off also hides a project's Enterprise Repository tab; References off
  hides its Reference tab.
- A fresh installation starts with all three on. (Leaving out services such as Documents stays with the optional
  services switches, `eax service`.)

## Checks

1. System admin › System settings: three switches at the end, all On.
2. Switch **Projects** off and save: the page reloads; the menus, the start page and Architecture work show no projects
   (Architecture work shows models only); Repository and References are gone too and the settings say "Off for now:
   Projects is off". Opening `#/projects/...` says Projects are switched off.
3. Try switching References on while Projects is off: refused with "needs Projects".
4. Switch Projects on again: everything is back as it was, with its data.
5. Switch **Repository** off only: the Repository menu and tile, and the project's Enterprise Repository tab, are gone;
   Project admin › Principles still opens.
6. Switch **References** off only: the Reference library and the project's Reference tab are gone.
7. With Projects off, the MCP project tools answer that Projects are switched off.

