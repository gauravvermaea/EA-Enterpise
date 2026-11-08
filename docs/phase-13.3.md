# Phase 13.3 — Turn Projects, Repository and References on or off (requested, for later)

Status: **requested for later** (owner, 8 Nov 2026). Not designed or built yet; discuss before building.

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
