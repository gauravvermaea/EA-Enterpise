# Phase 16.3 — Guided wizards (D181, D339)

Status: **built 8 Nov 2026; accepted and closed 9 Nov 2026 (D356).** The owner asked for all of them to be built without a
question each ("just get them all done"): the choices made are written under each wizard.

## Already built (not in this phase)
Set up, copy and merge a model; extend the metamodel; baseline (tag), publish and promote, archive (Model admin,
13.0.4); add models to a project, finish a project (13.0.1); give people access, back up and restore a model or the
whole estate (System admin, 8.4 and 13.0.4; the console, 13.5). Compare and gap analysis are screens with their steps.

## To build
| Wizard | What it is for |
|---|---|
| WIZ-021, WIZ-022 Data quality improvement and staleness | Walk through what the quality screen finds (missing values, broken rules, stale entities, entities with no owner) and fix it step by step |
| WIZ-019 Architecture compliance review | Review a solution against the principles and standards: findings, dispensations, a recorded result in the governance log |
| WIZ-017 Migration plan from gaps | Turn a gap analysis into work packages and a transition roadmap |
| WIZ-018 Collect data from people | Send stakeholders a sheet for their part of a model; review and take in what comes back |
| WIZ-013 Load data into a model | Pick the model and types, download the sheet, fill it, upload, preview, apply (on the import sheets of 10.1) |
| UI-009 First-run setup | A new installation's first Super Admin walked once through the essentials: template libraries, the charter and principles, the first people |

## How each works (choices made while building)

**Improve data quality (WIZ-021, WIZ-022)**, Model admin › Data and quality (or the model's Wizards tab). The model is
measured when the wizard opens, so it works on the model as it is. Choose what to work through (missing values, broken
rules, not checked for a long time, connected to nothing), a type, only the important ones, only mine; then one entity
at a time: fill in the missing fields (each as data entry shows it: a pick list as a drop-down, a date as a date), mark
them not applicable with a reason (a Model Admin approves), **Still correct** for a stale one (a Model Admin marks it
current, the person responsible attests it), or skip; rules and relationships are fixed on the entity (a link opens
it). What is typed becomes the person's uncommitted changes, committed as any change.

**Architecture compliance review (WIZ-019)**, Project admin › On a project (or the project's admin page). The solution
or change reviewed, what was looked at, its owner; then each of the project's principles and standards (retired ones
left out) with a verdict (Complies, Partly, Does not comply, Not applicable) and a note; the result is worked out
(Not compliant when anything is not met, Compliant with conditions when something is partly met, else Compliant) and
logged as a **Compliance assessment** in the governance log with the whole table (a draft: sent for approval as any
record); for each principle or standard not met, a **Dispensation** can be requested at once, pointing at it.

**Plan the migration from gaps (WIZ-017)**, Model admin › Data and quality, on a project model holding a gap analysis.
Choose the analysis and a first grouping of its open gaps (per domain, per entity type, per resolution, or one per
gap; gaps already in a work package are left out); rename the packages, give each a wave, dates and a resolution, move
gaps between them; then **Work Package entities** are made in the model and committed at once (Model Admins; the
metamodel needs a Work Package type, as ArchiMate 4 has), each associated with the elements its gaps are about; each
gap points at its work package and takes its resolution when it has none. Optionally the roadmap (wave, work package,
dates, resolution, gaps, counts) becomes a **tracking sheet** in a project. Server: `gaps.suggest_packages`,
`gaps.migration_plan`; `GET/POST /api/v1/gaps/<analysis>/migration-plan`.

**Collect data from people (WIZ-018)**, Model admin › Data and quality, Model Admins. Choose the entity types and the
people (only those whose role on the model changes its content; others are given access first), a note and a date.
Each person gets a request in their bell whose link opens the model's Import and export tab with those types chosen;
they download, fill in and upload; the rows become their changes, which they ask to be committed, and the Model Admin
reviews them as any commit request. Nothing new is kept: the request is the notification. Server: `eax/collect.py`;
`GET/POST /api/v1/models/<m>/collect`.

**Load data into a model (WIZ-013)**, Model admin › Data and quality. How it works, then the download (types and
format) and the upload of the Import and export tab (10.1), in three steps; the preview opens after the upload.

**First-run setup (UI-009)**, on the start page for a Super Admin until it is put away, and System admin › Wizards ›
Set up. Seven steps, each with a link to its screen: application settings, people and their roles, the parts in use,
template libraries, the organisation's charter, its principles, when backups run. A step is ticked when the
installation shows it (application settings changed, a template library confirmed, the charter approved) or when it is
marked done. Kept in core.settings under first_run. Server: `eax/first_run.py`; `GET/POST /api/v1/admin/first-run`.

## Checks
1. `.\eax clean-restart`, Ctrl+F5, signed in as a Super Admin: the start page shows **Set up this installation**; mark a
   step done, open one, put it away; System admin › Wizards › First-run setup opens it again.
2. Model admin › **Improve data quality** on Karoo Re (independent): it measures, lists what is found; fill in a field
   on one entity (a drop-down for a pick list), mark one not applicable, mark a stale one still correct, skip one; the
   summary at the end; the Changes tab holds what was typed.
3. Make a gap analysis in a project model (Compare › Gap analysis), then Model admin › **Plan the migration from
   gaps**: group, rename, date; make them with a roadmap sheet in a project: the Work Package entities are in the model
   (committed), the gaps point at them, the project's Sheets tab has the roadmap.
4. Model admin › **Collect data from people** on Karoo Re: choose a type and two people (one who cannot load is greyed);
   sign in as one of them: the bell has the request; its link opens Import and export with the type chosen.
5. Model admin › **Load data into a model**: download, change a value, upload: the preview opens.
6. Project admin › **Architecture compliance review** on a project with principles: verdicts, one not met with a
   dispensation; the governance log has the Compliance assessment (with its table) and the Dispensation.
