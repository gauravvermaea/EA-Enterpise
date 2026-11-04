# Notes for AI agents working on EA Explorer

Read this first. It is enough to pick the work up with no earlier conversation. `CLAUDE.md` points
here.

## What this is

EA Explorer: an open-source enterprise architecture repository (like Orbus iServer or LeanIX). Docker
Compose stack: Flask API with job runner and MCP server, PostgreSQL, Keycloak, Superset, Mayan EDMS,
draw.io, nginx, React screens. How it is built: [docs/architecture.md](docs/architecture.md).

## How the owner works (must follow)

- **You write code only.** The owner (Gaurav) runs Docker, installs things and pushes to GitHub. Do not
  install software on his machine or run the stack for him.
- **Do not build anything until asked.** Discuss and plan first when a request is open.
- **Always a clean rebuild** (`.\eax clean-run`); no in-place patches or hand fixes to a running system.
- Everything that creates the database is code in this repository; nothing by hand.
- Plain language in screens and docs; British spelling.
- Everything goes through nginx (D107): publish no other port. Keep the start page cards (`services.js`) in step with the build plan (D109).
- Mark models with `ModelMarks.jsx` (kind, library, read-only, locked; D102) wherever models are listed.
- Record each decision in `docs/decisions.md` (next number after the last D), open items in
  `docs/todo.md`, and each phase in `docs/phase-N.md` (what it delivers, demo, checks, upgrading, not
  in this phase). Keep this file and `docs/architecture.md` current every phase (D76).
- Requirements and plan: `docs/requirements/EA_Explorer_Requirements.xlsx` and
  `EA_Explorer_Build_Plan.xlsx` (generated; update them when scope changes).

## Rules the product keeps (do not break)

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
| 3.1 Roles and permissions: global roles from Keycloak, roles per model, row-level security, break-glass; the Root model at the top and a root metamodel built from scratch; library browser; model marks; https through nginx with eax trust; start page shows what is coming | 0.3.1 | built, waiting for the owner's test |
| 4 Model hierarchy (root metamodels), models and deep copy | 0.4.0 | next |

The full plan (46 phases) is in the build plan workbook. Agreed but not yet built, with their
decisions: commits and merge screens (D61, D66), Mayan phase (D62), lineage (D63), dedupe per model
(D68), change log report (D69), view templates (D70), report designer (D71), complete backup and restore
from the web (D74), dynamic import, export and survey sheets (D77, format still open), collection
sets with staging (D78), data entry page (D79), the model hierarchy: the Root model, root metamodels with framework and version, derived models (D81, phase 4), moving a model to a new framework version (D82), actions, alerts and workflows with metamodel push-down and change documents (D83-D86, phase 8.1), integration and a drag-and-drop ETL tool still to be chosen (D91, phase 34.1). Roles settled: only Model Admins change the metamodel (D89); they also edit and commit content (D90). Library models: create as a library model with a pack, promote to the library, download and upload as one package (D101, phase 4). Architecture projects loosely coupled to models, with their ADM phase, organisation-wide and project registers (principles, decision and governance logs) and artefacts produced from library templates, reviewed and stored (D103-D105, phases 15 to 16.2, design session first; open questions in docs/todo.md). AD sign-in, scale-out, another identity platform, auth and paths in the config file and a key vault for passwords are productionising stories for the final deployment scripts (D99, phase 36; docs/todo.md).

## Testing without Docker (what earlier agents did)

There may be no Docker in an agent's sandbox. What worked:

- A throwaway PostgreSQL 16 (`pg_ctl`), run the SQL in `migrations/sql` in order plus the seed, then
  `tests/sql/phase*_checks.sql`.
- `pytest -q` in `services/api` (the tests that need Flask itself need the real packages).
- For the screens: bundle `services/web/src` with esbuild, serve with a small Python server that maps
  `/api/v1/...` routes to `eax.repository` / `eax.metamodel_edit` functions, and take Playwright
  screenshots. Check every screen you change.

## Handing back

List the files changed, say what the owner should run (`.\eax clean-run`, the checks in the phase
note) and what to look at. Keep messages short.
