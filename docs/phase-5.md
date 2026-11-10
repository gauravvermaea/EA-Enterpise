# Build phase 5: report views and the thirty standard reports

Goal: everything in the repository can be reported on, in Superset or any SQL or BI tool, for the
models a person has; and the thirty standard reports of the requirements (phase 11 brought forward,
D137) ship as Superset dashboards. Version **0.5.0**, migration `0009_reports`. Decisions D137 to D142.

## Status: accepted and closed (owner, 4 Nov 2026, D143); each of the 32 dashboards is checked in the end-to-end testing phase, 36.1

## What phase 5 delivers

- **Report views** in schema `rpt`, read by the read-only report login `eax_report`:
  - generic views, the same for every model: `rpt.models`, `rpt.entities`, `rpt.entity_values`,
    `rpt.relationships`, `rpt.changes` (two years), `rpt.entity_pairs` (both ends of every relationship),
    `rpt.entity_std` (one row per entity with the common attributes), `rpt.catalogue`;
  - **typed views**, one per entity type: `rpt.t_<type>` (e.g. `rpt.t_application_component`) with the
    entity's own columns and one column per attribute. Made again after every metamodel change and
    after the seed, only where something changed (D139);
  - the **report catalogue**: every type and attribute with the view and column it is in (D71).
- **Model access for reports** (D138): a report runs on one or more models. The Model filter on every
  dashboard lists only the models the person has in EA Explorer (their model roles, the models above
  them, the published library; a Super Admin every model), several at a time. Inside a model they see all
  of its data; nothing is filtered per record. Superset's IT Admins and Keycloak Admins see no content.
- **Thirty-two dashboards** (Superset, *Dashboards*, certified "EA Explorer"), each with the Model filter:

  | Code | Report | Charts |
  | --- | --- | --- |
  | MO | Model overview | entities by domain and type, models, changes in the last 90 days |
  | SR-01 to SR-08 | Inventories: applications, capabilities, technology, data, processes, interfaces, actors, motivation | a summary pivot and the full list with *Open* links |
  | SR-09 to SR-15 | Matrices: application against capability, process, data (CRUD), technology; process against role; capability against value stream; application interactions | the matrix and the relationships behind it |
  | SR-16, SR-17 | Capability heatmap; technology lifecycle and end of life | heatmap pivots, end-of-life list |
  | SR-18 to SR-21 | TIME quadrant; criticality against technical health; cost by capability; vendor concentration | quadrant pivots, bars, lists |
  | SR-22 to SR-25 | Impact analysis (with a *Chosen entity* filter); obsolescence risk; single points of failure; rationalisation candidates | pivots, ranked lists |
  | SR-26 to SR-28 | Completeness by type and owner; orphans; duplicate candidates | completeness %, lists |
  | SR-29, SR-30 | Change activity; comparison with the source model | weekly line, pivots, differences |
  | HM | Pick-list heatmaps | values of every pick list by type and attribute |

  Standard reports work on any model that keeps the standard types (`rpt.std_roles`, D140).
- **Filters you set yourself** on every dashboard (D141): the Model filter (several models at a time), drop-downs
  for type, domain, owner, lifecycle, vendor, changed by or status where the report has them, number
  ranges for its measures (criticality, cost, fit, applications, dependants, completeness, similarity,
  steps away) and a time range where it has dates. **Threshold pickers** on the heatmaps and banded
  reports re-band the cells at once: SR-16 and the pick-list heatmaps *Medium from* and *High from*,
  SR-17 *Red within* and *Amber within* (months), SR-23 *High within* and *Medium within* (months).
  Nothing is stored; to keep a variation, save your own copy of the chart or dashboard in Superset.
- **Reports tab** on every model page: a card per dashboard (opens in Superset), which of the model's
  types each report uses, and the report catalogue with a CSV download.
- **MCP**: `get_report_catalogue(model)`.
- ArchiMate 4 template: Application Component gains **TIME**, **Functional Fit** and **Technical Fit**
  (for SR-18 and SR-19); the sample's applications and database cluster have values for them.

## Demo

1. `.\eax clean-restart` (new migration and seed attributes).
2. Sign in as `user_report_viewer`, open **Models > Sample insurance model > Reports**: the cards and
   the catalogue (expand *Application Component*: TIME, Functional Fit, Technical Fit and their columns).
3. Press **SR-01 Application portfolio inventory**: Superset opens (sign in with Keycloak once). In the
   Model filter only *Fynbos Mutual (group)*, *Sample insurance model* and the library models are listed.
   Choose two models: the summary gives each its own rows. *Open* in a row goes back to the entity.
4. **SR-18 Application TIME quadrant** on *Sample insurance model*: Policy Administration System in
   *Migrate*. **SR-23 Obsolescence risk**: the Production Database Cluster (end of life April 2027)
   and the application on it.
5. **SR-22 Impact analysis**: choose a model, then an entity in *Chosen entity*; narrow *Steps away* to 1–2.
   **SR-16 Capability heatmap**: set *Medium from* to 1 and *High from* to 2: the bands change at once.
   **SR-17**: set *Red within* to 6 months: the database cluster moves to Red.
6. **SR-30 Comparison with the source model** on *Fynbos Life*: what differs from *Fynbos Mutual (group)*.
7. Sign in as `user_it_admin` and open Superset: no dashboards' data (IT Admins see no content).
8. As `user_model_admin`, add an attribute to a type in *Fynbos Life* (Metamodel tab): its typed view
   gets the new column at once; the Superset dataset follows at the next start.

## Checks

- `tests/sql/phase5_checks.sql`, as the API's login, with the sample loaded. Ends with "phase 5 checks passed".
  ```powershell
  Get-Content services/api/tests/sql/phase5_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
  ```
- Earlier phases' checks still pass.
- `pytest services/api/tests`: `test_reports.py` (every report has its view, every chart uses columns and
  metrics its dataset has, one bundle per report, the Model filter allows several models, the Superset
  roles and model access).
- `docker compose logs reports-init`: one "importing report" line per dashboard, then
  "report datasets ready (... datasets ...); model access on ... datasets".

## Upgrading from phase 4

`.\eax clean-restart`. The setup service writes one bundle per dashboard to the rendered volume; the
reports-init service imports each, adds the typed datasets, the role *EA Explorer reports* and the
model access rule. Superset's settings turn on template processing (for model access) and map
Keycloak roles to Superset roles afresh at every sign-in.

## Not in phase 5

- Typed views are added to Superset at the next start of reports-init (`.\eax up`); the database views
  follow a metamodel change at once.
- Change sets and their source (web, CSV, diagram, MCP, merge) in SR-29: phase 8. Named versions and
  baselines in SR-30: phase 24.1. Dedupe actions on SR-28's candidates: phase 21.
- The report designer and saved report layouts (D71): later; for now build new charts in Superset on the
  report views.
- Governance and operations dashboards: with their phases (16, 35).

## Test checklist (for the end-to-end testing phase, 36.1)

- [ ] Reports tab: 32 cards, standard roles line, catalogue with CSV.
- [ ] Each of the 32 dashboards opens with data on the sample or the reference model.
- [ ] Model filter lists exactly the person's models; several can be chosen; IT Admin sees none.
- [ ] Threshold pickers re-band SR-16, SR-17, SR-23 and the pick-list heatmaps; ranges and drop-downs filter.
- [ ] A metamodel change makes or drops a typed view; a second refresh changes nothing.
- [ ] `get_report_catalogue` through MCP.
