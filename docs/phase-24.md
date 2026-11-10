# Build phase 24: KPI trends, the OData feed and the report designer

Goal: see how each model moves over time, let Power BI and Excel read the repository directly, and let people build
their own report data without SQL. Version **0.17.0** (batch 1, D421), migration `0035_kpi_odata_reports`. Design agreed
with the owner on 9 Nov 2026 (D365); built 10 Nov 2026, decisions D430 to D436.

## Status: built, to be accepted

## What phase 24 delivers

- **KPI trends (D430, D431)**, a **KPIs** tab on every project and library model:
  - a **standard KPI set**: Entities; Entities by type; Applications by TIME; Applications by lifecycle; Total annual
    cost; Data quality score; Orphans; Technology past end of life; Technology reaching end of life within 12 months.
    They follow the standard roles and attribute codes the standard reports use (D140), so they work on ArchiMate 4,
    its copies and the reference models;
  - **kept as snapshots on the 1st of each month** (the job runner checks every hour; a month missed while the server
    was off is taken when it is back, dated the 1st) and **on every tag** (the snapshot is named after the tag). A
    model's first snapshot is taken in the month it is first seen. Archived and frozen models are not snapshotted
    (D360). Committed content only;
  - shown as a table (value **now**, worked out live; the change since the last snapshot; a small trend) and, for the
    KPI chosen, a chart with one line per part (type, TIME class, lifecycle), tags marked, and the last values by part;
  - the same data in the reporting tool: report **KR-01 KPI trends** (choose the KPI and the models; one line per model
    and part) over `rpt.kpi_trends`.
- **A model's own KPIs (D432)**, set by its **Model Admins** (and Super Admins) on the KPIs tab: a **count** of the
  entities of a type, or the **sum** of a number attribute, with **one filter** (is, is not, contains, is empty, is not
  empty, more than, less than; numbers and dates compare as numbers and dates). Kept from the next snapshot; the value
  now shows at once (marked *new* until it has a trend). **Stop keeping it**: its trend so far stays (marked *no longer
  kept*).
- **The OData feed (D433)**: one per model, `https://<host>/api/v1/odata/models/<model id>/`, shown on Reports > Report
  designer with a Copy button. OData version 4 (JSON), read only:
  - tables: one per entity type (named after its code, e.g. `ApplicationComponent`), with the standard columns (Id,
    DisplayId, Name, Description, EntityType, Domain, ParentId, Parent, Status, created and changed, Link) and one
    column per attribute; plus **Entities** (every entity) and **Relationships** (both ends by id and name);
  - `$metadata`, `$select`, `$filter` (eq, ne, gt, ge, lt, le, and, or, not, parentheses, contains, startswith,
    endswith, null, true, false), `$orderby`, `$top`, `$skip`, `$count`; pages of 5,000 rows with a next link;
  - **signed in, with the person's own permissions**: rows are read as the person, so row-level security gives only
    the models they may read. In Power BI or Excel: *Get data > OData feed*, paste the address, choose **Basic** and give
    the EA Explorer user name and password. The password is checked by Keycloak (client `eax-odata`, password grant only,
    no browser sign-in) and never kept; the answer is remembered for four minutes so a refresh does not ask Keycloak for
    every page. A Bearer access token works too.
  - **Machine access (phase 25)** plugs in through `eax/odata_auth.py`: `CHECKS` is a list of functions
    `(user name, secret) -> User or None`, tried before Keycloak, so an API key or personal token sent as the Basic
    password works without changing the feed; Bearer credentials go through `eax.auth.current_user` like every call.
- **The report designer (D434)**, Reports > **Report designer**: choose an entity type, its columns, up to four related
  types (through a relationship type the metamodel allows, either way) with their columns, and up to ten filters; **Show
  the first rows** (the count and 20 rows, and the query); **Save**; **Save and open** opens the reporting tool. Designs
  are kept on the model (whoever made one, or a Model Admin, changes or deletes it). The SQL is made from names checked
  against the report views' own columns, and values written as quoted literals: nothing typed reaches the query as SQL.
  It reads the typed report views (`rpt.t_<type>`, D139) and `rpt.relationships`, limited to the model.
  - **Open** goes to a small page in the reporting tool (`/eax/designs/<id>/open`, `deploy/superset/eax_designer.py`,
    signed in through Keycloak as the person): it checks the person has the design's model (`rpt.model_access`, D138),
    makes or refreshes the design's dataset (SQL on the report connection, named *Designed: <name> [<id>]*), gives the
    readers' role access, puts it under the model-access rule, and opens Superset's **chart builder** on it. Charts and
    dashboards are then made in Superset as usual. Scheduled reports stay dropped (D365).
- **Backups (D435)**: a model package and a model backup carry the model's own KPIs, its snapshots and its report
  designs (`reports/reports.json`); restoring as a new model or over itself puts them back. Infrastructure backups have
  them in the database dump (D410).
- **Sample data (D436)**, laptop: the demo estate has a year of monthly snapshots (growing, orphans and end-of-life
  technology falling, quality rising; illustrative numbers), the snapshots its two tags take, two own KPIs with history
  (a count with a filter, a sum with a filter), one added since the last snapshot (no trend yet) and one no longer kept;
  the other models have none until the job runner takes their first.

## Where it is

| Part | Files |
|---|---|
| KPIs | `services/api/eax/kpis.py`, the job `eax.kpi_monthly` (`eax/jobs.py`), the tag hook (`eax/tags.py`) |
| OData | `services/api/eax/odata.py`, `eax/odata_auth.py`, client `eax-odata` in `deploy/keycloak/realm-eaexplorer.json.tmpl` |
| Designer | `services/api/eax/report_designer.py`, `deploy/superset/eax_designer.py` (loaded by `superset_config.py`) |
| API | `services/api/eax/api/kpi_reports.py` |
| Reports | KR-01 in `eax/report_defs.py`, `eax/setup/superset_reports.py`, `eax/report_about.py` |
| Database | `migrations/sql/0035_kpi_odata_reports.sql`: `core.kpi_definitions`, `core.kpi_snapshots`, `core.kpi_values`, `core.report_designs`, `rpt.kpi_trends`, `rpt.report_designs` (rows only, D248) |
| Screens | `services/web/src/Kpis.jsx` (KPIs tab), `ReportDesigner.jsx` (designer and OData address), `ModelReports.jsx` |
| Seed | `services/api/eax/seed/sample_kpis.py` (step *Sample KPI trends on the demo estate*) |
| Tests | `services/api/tests/test_kpi_reports.py` |

## API

| Call | What it does |
|---|---|
| `GET /api/v1/models/<m>/kpis` | every snapshot and the value now, by KPI and part |
| `POST /api/v1/models/<m>/kpis/definitions`, `PUT .../<kpi>`, `POST .../<kpi>/delete` | the model's own KPIs (Model Admins) |
| `GET /api/v1/models/<m>/report-designer` | types, columns, related types, the saved designs and the OData address |
| `POST /api/v1/models/<m>/report-designs`, `PUT .../<d>`, `POST .../<d>/delete`, `POST .../preview` | designs |
| `GET /api/v1/odata/models/<m>/`, `$metadata`, `<Table>` | the OData feed |

## Checked here, and what needs the laptop

Checked in the preview against a fresh database: the KPIs tab (table, trends, chart by part, adding a KPI), the report
designer (choosing columns, a related type, a filter, the first rows, saving) and the OData answers (tables, `$metadata`,
`$filter`, `$select`, `$orderby`, paging). Superset cannot run here, so on the laptop check: report KR-01; **Save and
open** making the dataset and opening the chart builder as a non-admin user (only their models); and Power BI or Excel
reading the feed with Basic sign-in (Keycloak's new `eax-odata` client comes with the clean restart's realm import).

## Decisions

D430 to D436 in [decisions.md](decisions.md).
