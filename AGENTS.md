# Notes for AI agents working on EA Explorer

Read this first. It is enough to pick the work up with no earlier conversation. `CLAUDE.md` points
here.

## What this is

EA Explorer: an open-source enterprise architecture repository. Docker
Compose stack: Flask API with job runner and MCP server, PostgreSQL, Keycloak, Superset, Mayan EDMS,
draw.io, nginx, React screens. How it is built: [docs/architecture.md](docs/architecture.md).

## How the owner works (must follow)

- **You write code only.** The owner (Gaurav) runs Docker, installs things and pushes to GitHub. Do not
  install software on his machine or run the stack for him.
- **Do not build anything until asked.** Discuss and plan first when a request is open.
- **Always a clean rebuild** (`.\eax clean-run`); no in-place patches or hand fixes to a running system.
- Everything that creates the database is code in this repository; nothing by hand.
- Plain language in screens and docs; British spelling.
- Never name another EA platform or vendor product in the code, screens, docs or workbooks (D114); requirements from
  reviewing commercial products carry the source "Market review".
- Everything goes through nginx (D107): publish no other port. Keep the start page cards (`services.js`) in step with the build plan (D109).
- Mark models with `ModelMarks.jsx` (kind, library, read-only, locked; D102) wherever models are listed.
- Record each decision in `docs/decisions.md` (next number after the last D), open items in
  `docs/todo.md`, and each phase in `docs/phase-N.md` (what it delivers, demo, checks, upgrading, not
  in this phase). Keep this file and `docs/architecture.md` current every phase (D76). Every phase also gets a row, with its name, in the Build phases table of `README.md`.
- Requirements and plan: `docs/requirements/EA_Explorer_Requirements.xlsx` and
  `EA_Explorer_Build_Plan.xlsx` (generated; update them when scope changes).

## Rules the product keeps (do not break)

- **Avoid logic in the database where possible (D248)**: rules, calculations and checks go in Python; no new triggers or
  database functions for them. Heavy calculations run as background jobs and are stored; screens show the last result
  with its date (only a single entity is checked at once).
- Checks warn, never block (D48); a metamodel change is never blocked by existing content (D64).
- A retired entity type's entities are read-only until it is restored (D87, database trigger).
- Nothing is hard-deleted: `is_deleted` plus `history.row_versions`; removed values stay in history (D75).
- Shipped root metamodels (Root, ArchiMate 4) and reference models are locked by the database (`is_locked`, only `eax_migrator` passes).
- Model locks (`lock_level`) are enforced by triggers, not only the screens (D67).
- One metamodel change publishes one metamodel version (D72).
- The SQL window is read-only (D52).
- Permissions are enforced in the API (`eax/permissions.py`) and again in the database (row-level security
  and triggers, 0006); every API connection is told who is asking (`eax/db.py`). Global roles are given in
  Keycloak and mapped to ours (D92); roles on a model are given per model in EA Explorer (D96). Never add a route that skips `require_auth`.
- Every REST endpoint is in Swagger (flask-smorest schemas); reads live in `eax/repository.py` and are
  shared with the MCP server.
- Last write wins for repository content; no concurrent-edit locking (D55).

## State of the build

| Phase | Version | State |
| --- | --- | --- |
| 0 Platform | 0.0.x | closed |
| 1 Metamodel, read only | 0.1.0 | closed |
| 2 Reference model, locked models, library, versions, graphs, timeline | 0.2.1 | closed 4 Nov 2026 |
| 3 Metamodel editing, versions and history, failing checks, model locks | 0.3.0 | accepted 4 Nov 2026 |
| 3.1 Roles and permissions: global roles from Keycloak, roles per model, row-level security, break-glass; the Root model at the top and a root metamodel built from scratch; library browser; model marks; https through nginx with eax trust; start page shows what is coming | 0.3.1 | accepted 4 Nov 2026 |
| 4 Creating and copying models (child or independent), root metamodels, library models (Library Admin), packages (zip and Excel) with an upload wizard, framework move, archive and delete, metamodel drafts by AI through MCP | 0.4.0 | accepted and closed 4 Nov 2026 (D136); end-to-end test in 36.1 (D129) |
| 5 Reports: report views (generic and typed per entity type), model access for reports (several models at a time), Superset dashboards for the model overview, all thirty standard reports SR-01 to SR-30 (from phase 11) and pick-list heatmaps, the Reports tab with the report catalogue | 0.5.0 | accepted and closed 4 Nov 2026 (D143); each report checked in 36.1 |
| 6 Data entry in forms: forms from the metamodel, Data entry tab (D79), edit, retire, restore, delete, relationships inside and outside the metamodel (D49), tags, rule overrides (D48), roll back | 0.6.0 | accepted and closed 4 Nov 2026 (D146); end-to-end test in 36.1 |
| 7 Grids for entities, relationships and the metamodel (paste from Excel), search, saved views, favourites and recent items | 0.7.0 | accepted and closed 4 Nov 2026 (D157); end-to-end test in 36.1 |
| 8.2 Reports and views, pulled ahead of 8 (D161): viewpoints as data (VP-01 to VP-25 and your own), Viewpoints tab (diagram, catalog, heat map, matrix, relationships), value stream map and roadmap, TOGAF catalogues TC and matrices TM, dependency reports DR, audience dashboards AU (D153), richer Superset charts, the demo estate Protea Insurance | 0.8.2 | accepted and closed 5 Nov 2026 (D164); each report checked in 36.1 |
| 8 Commits (D165 to D170): content private to its author until committed, change sets replayed at commit (eax/commits.py), Committer and History Viewer roles, Changes tab, conflicts at commit, roll back as a new commit, entity page highlights and commits its changes, draft reject and reopen, merge upload (eax/merge.py), batch endpoint for diagram saves, live update banner. Every content write must go through eax.commits for project models | 0.8.3 | accepted and closed 5 Nov 2026 (D171); end-to-end test in 36.1 |
| 8.3 Tags, comparison and gap analysis (D172, D173): frozen snapshots in core.model_tags (eax/tags.py: snapshot, restore as a complete override with an automatic tag first), comparison (eax/compare.py: sides, filter screen, matching, Excel), TOGAF gap analyses (eax/gaps.py: templates, gaps, Gap entities, Excel and Word), Tags tab and page per tag, Compare and Gap analyses as top-menu screens with gaps stored in a chosen model (D177, Versions.jsx), demo data made after start (eax/seed/versions_demo.py), reports GR-01 to GR-05 | 0.8.4 | built 5 Nov 2026, waiting for the owner's test |
| 9 Change log (D180): one row per action in its own database (EAX_CHANGELOG_DB_URL, schema changelog), shipped in the background from history.row_versions and audit.events once their transaction finished (eax/change_log.py, `python -m eax.change_log` in entrypoint.sh); never write to it from a request; API actions to log are listed in change_log.ACTIONS; screen ChangeLog.jsx | 0.9.0 | built 5 Nov 2026, waiting for the owner's test |
| 10 Administration console (D183): core.settings (eax/settings.py: runtime settings applied at once, start-up settings shown masked), Admin.jsx, fmt.js (every date and number through the installation's settings, D182: never toLocaleString), operations helper services/ops (Docker engine, EAX_OPS_TOKEN, restart only), "About this report" section on every report (eax/report_about.py, D186), VP-26 Gap (D185) | 0.10.0 | built 5 Nov 2026, waiting for the owner's test |
| 10.1 Import and export sheets (D197): eax/sheets.py (build on the fly, read back), eax/sheets_vba.py (.xlsm: VBA project to [MS-OVBA]/[MS-CFB]), eax/loads.py (preview, add as the owner's uncommitted changes, undo, column mappings; feeds and collection sets: phase 34, D198), eax/api/sheets.py, Sheets.jsx; background tasks eax/tasks.py (D192) | 0.10.1 | built 5 Nov 2026, waiting for the owner's test |
| 12.1 Start-up in two tiers (D255): core seed only before the API (eax/seed/__main__.py), the rest after it (eax/seed/later.py: sample and test models step by step via build.test_model_steps, demo estate, first quality measurement; progress in core.startup_parts, migration 0021_startup); eax/startup.py once; eax/startup_status.py and /api/v1/startup, /api/startup; eax.ps1/eax.sh Get-Tiers, Wait-Core, start-later, --wait-all; Keycloak health check; StartupStatus.jsx (header, Administration > Containers). Open in draw.io (D256): exporting.js openDrawio/openDrawioXml (#R compressed). Grid commit icon (D257) | 0.13.1 | built 6 Nov 2026, waiting for the owner's test |
| 13 Architecture projects (D258-D263): schema proj (migration 0022_projects): lib_* library tables loaded on every start by eax/seed/project_library.py from project_library.json (built by tools/build_project_library.py from docs/requirements/EA_Explorer_Master_Template_Repository.xlsx; never hand-edit the JSON), project tables. eax/projects.py holds every rule (roles, _need, create, repository build, documents, check-out); eax/mayan.py talks to Mayan's REST API v4 as one service account; eax/api/projects.py; jobs project_repository and project_repositories (every minute). Projects.jsx (list, wizard, project page, ProjectLibraryAdmin). Template libraries (D264): template_libraries/lib_templates; EA Explorer's own files in library/templates/ea-explorer built by tools/build_ea_explorer_templates.py (never hand-edit; mounted at /data/ea-explorer-templates), others in Mayan; uploaded zips loaded by the template_library_load job; proj.template_setup gates create(). D266: proj has its own engine (db.get_projects_engine, EAX_PROJECTS_DB_URL); never join proj with another schema or add a foreign key across; reach core through projects.core(conn) / projects.connections(). TOGAF template files are licensed: never commit library/templates/togaf, never put their content in code | 0.14.0 | built 6 Nov 2026, waiting for the owner's test |
| 13.0.1 Setting up and running a project (D274-D279): migration 0024_project_setup. eax/project_work.py holds the new rules (scope_fields, clean_html, goals/write_goals as Goal and Outcome entities tagged project:<guid> in the home model, viewpoint_status/add_viewpoint (PV-n), update = the edit workflow, project files, sign-off raise/decide/record/withdraw_open, finish_check/finish). projects.py: link_model, model_roles, item_templates, item_templates_all, placeholders honoured by build_repository; _need refuses writes on frozen/merged projects. Background kinds project.updated and project.finished (eax/background.py, _projects_beside keeps proj and core in one transaction). Web: Projects.jsx (wizard models first, Landing with AdmWheel.jsx, SignoffTab, FinishDialog), RichText.jsx. Never use the word objective: Outcome | 0.14.2 | built 7 Nov 2026, waiting for the owner's test |
| 13.0.3 Model roles and project templates (D281, D282): migration 0025_project_templates (project_models.role/role_seq, proj.project_templates, projects.template_code). eax/project_templates.py (ROLES, listing, clean_spec, save, from_project); the 14 templates in eax/seed/project_templates.json (added once by library_sql). Web: Gallery, applyTemplate, RoleSlots, RoleSelect, ProjectTemplatesAdmin in Projects.jsx. New proj tables need the eax_migrator GRANT block (see 0022/0024/0025). The wizard makes no gap analyses (owner) | 0.14.3 | built 7 Nov 2026, waiting for the owner's test |
| 13.0.4 Admin by wizards, five areas (D283-D285): migration 0026_model_wizards (core.models frozen_at/by/note; set_lock and clear_lock refuse a frozen model). eax/model_wizards.py (tag_first, freeze/unfreeze, detach/reparent, split, extend_preview/extend_metamodel, duplicates/merge_duplicates, hand_over, family), eax/api/model_wizards.py, merge.apply(exclude) with merge._select, background kinds wizard.merge/split/extend; project finish offers merge-freeze and freeze. Web: Areas.jsx (AREAS, AreaMenu, AreaTiles, ArchitectureWork), ModelAdmin.jsx (wizards, MergeWizard by type then by item), SystemWizards.jsx, ProjectAdmin in Projects.jsx, Duplicates in Quality.jsx; Metamodel.jsx ADMIN_VIEWS redirect to #/model-admin. Admin is wizards, architecture is screens: no admin buttons on the model or project page | 0.14.4 | built 7 Nov 2026, waiting for the owner's test |
| 13.0.5 Common analysis (D286): migration 0027_common_analysis (core.common_analyses, common_items, common_runs). eax/commons.py (match with by_display_id off by default, analyse: side-by-side clusters, threshold, values, relationships, suggestions; create/refresh/decide_suggestions/update_items/tag_common/make_model via model_wizards.split, to_xlsx/to_docx via gaps.docx_from), eax/api/commons.py, background kinds common.*. Web: Commons.jsx under #/compare/common (Versions.jsx tab) | 0.14.5 | built 7 Nov 2026, waiting for the owner's test |
| 13.0.6 The repository as a table (D290): migration 0028_repository_table (documents: user_version, out_version, tags, accepted_*, archived_*, deleted_*, state Accepted; items: not_needed_*, added_by; projects.signoff_quorum; signoff_requests.quorum). eax/projects.py: next_version, set_tags, accept, set_hidden, set_quorum, add_item, not_needed, documents(show), check-in needs what changed; eax/project_work.py: quorum_of, settle_state (any rejection rejects), withdraw_request; routes /items, /items/<i>/not-needed, /documents?show=, /documents/<d>/tags, /accept, /archive, /delete. Web: Projects.jsx RepoTable (phase tabs, compact on the landing), AddDocDialog (new class on the spot), AddClassDialog, NotNeededDialog, CheckInDialog, AcceptDialog, TagsDialog, Quorum, file-type filter in PhaseByPhase | 0.14.6 | built 7 Nov 2026, waiting for the owner's test |
| 13.0.2 Every slow button as a background task (D273): migration 0023_background (tasks.link/progress/progress_note, task_files.role input|result, notification category task). A slow route calls api/tasks.start(kind, model, label, params, link, inputs) unless api/tasks.waiting() (?wait=true); file routes keep GET and take ?background=true. The work of each kind is in eax/background.py (registered into tasks.WORK; return (message, result); result keys _action/_details steer the audit); tasks.run notifies the asker (category task) on done and failed; tasks.progress(pct, note) writes on its own connection; result files kept 24 hours (job task_files_cleanup). Web: tasks.js (runTask, downloadTask, startDownload, useAllTasks), TaskDrawer.jsx (the drawer, TaskFiles for a page's recent files), Notifications.jsx tab tasks. New slow buttons use the same: never a long request | 0.14.1 | built 6 Nov 2026, waiting for the owner's test |
