# Build phase 8.2: reports and views

Goal: any model through any view, the TOGAF catalogues and matrices, dependency reports and a dashboard for each
kind of reader. Version **0.8.2**, migration `0012_viewpoints`. Built before phase 8 (owner, 5 Nov 2026). Decisions
D147, D148 (in part), D149, D153, D161.

## Status: accepted and closed (5 Nov 2026, D164); each report checked in phase 36.1 (D129)

## What phase 8.2 delivers

- **Views as data, prefixed VP.** The 25 example views of the ArchiMate 4 Specification (Appendix C), in
  our own words: VP-01 to VP-13 basic (composition, support, cooperation, realization), VP-14 to VP-17 motivation,
  VP-18 to VP-22 strategy, VP-23 to VP-25 implementation and migration. Each has its concerns, stakeholders, purpose,
  element types, relationship types, the attribute its heat map colours by and the audiences it suits. Built-in
  views are fixed (the database refuses changes); **Library Admins add the organisation's own** (codes such as
  OVP-01), or copy a built-in one and change it.
- **Views tab** on every model: the views by category with how many of the model's entities each shows.
  Open one to see the model through it as a
  - **Diagram**: the elements in bands by domain with only the view's relationships (drag, zoom, .drawio, SVG, PNG);
  - **Catalog**: one row per element with owner, lifecycle, criticality, maturity...; CSV with every attribute;
  - **Heat map**: tiles grouped by type, parents holding their parts (a capability map by level), coloured by any
    attribute you choose, with a legend;
  - **Matrix**: any type of the view against another, the relationships in the cells; CSV;
  - **Relationships**: every relationship the view shows; CSV;
  - and **Open in the reporting tool**: the same view as a dashboard.
  The diagram, heat map and matrix download as **.drawio** files (each box linked to its entity), as do the value
  stream map and the roadmap; every view also downloads as CSV.
- **Business maps** in the Graph tab: **Value stream map** (each value stream as a chevron of stages with the
  capabilities that enable each stage, coloured by maturity or any attribute; or as a value stream x capability heat
  map) and **Roadmap** (plateaus, work packages and deliverables on a timeline, coloured by type, priority or
  architecture state, today marked).
- **Reports, 111 dashboards in the reporting tool**, each with the Model filter (several models at once):
  - the 32 standard reports, now with a data-flow sankey (SR-06), an application network (SR-15), a capability treemap
    (SR-16) and a portfolio bubble chart (SR-18);
  - **VP-01 to VP-25**: elements by type and lifecycle, a heat map with a *Colour by* filter, a network, a source x
    target matrix, the catalog and the relationships;
  - **TOGAF catalogues** TC-01 principles, TC-02 stakeholders, TC-03 driver to goal to outcome, TC-04 requirements,
    TC-05 locations, TC-06 products and services, TC-07 contracts and measures, TC-08 work packages and roadmap,
    TC-09 roles;
  - **TOGAF matrices** TM-01 business interaction, TM-02 actor and role, TM-03 role and application, TM-04 application
    and organisation, TM-05 location, TM-06 data and business function, TM-07 data security, TM-08 strategy and
    capability, TM-09 capability and organisation, TM-10 stakeholder and concern, TM-11 plateau and architecture,
    TM-12 service and process;
  - **Dependency reports** DR-01 dependencies of a chosen entity, up and down to six steps with the path; DR-02 a
    dependency matrix between any two types you choose; DR-03 impact chains from technology through applications,
    processes and capabilities to value streams, with end-of-life risk; DR-04 dependency counts and hot spots with
    thresholds you choose;
  - **Audience dashboards** AU-*: one per audience (CEO, CFO, CIO, CTO, COO, CRO, CISO, Chief Data Officer, Chief
    Compliance Officer, business, architecture, operations and control: 29 in all) with the headline chart of every
    report for that audience. Audiences are not roles and give no access (D153).
- **Reports tab**: the dashboards grouped by family, shown for one audience (remembered on this browser) or everyone,
  with a search.
- **MCP**: `list_views`, `model_through_view`, `value_stream_map`, `roadmap`.
- **Demo estate** (laptop): *Protea Insurance (demo estate)*, a fictitious insurer with 278 entities and 538
  relationships across every domain, with values for lifecycle, criticality, cost (USD), TIME, fit, end of life,
  classification, maturity and dates, so every view and report has data. Every company, product and vendor name
  is invented.

## Demo

1. `.\eax clean-restart` (new migration and demo model).
2. As `user_architect`: **Protea Insurance (demo estate) > Views**. Open **VP-19 Capability Map > Heat map**:
   capabilities by level coloured by maturity; colour by Criticality instead.
3. **VP-11 Application Cooperation > Diagram**, then **Matrix** (Application Component against Application Component),
   then **Open in the reporting tool**.
4. **Graph > Value stream map**: switch to *Value stream x capability*. **Graph > Roadmap**: colour by Priority.
5. **Reports**: *Reports for* CFO; open the **CFO dashboard**. Open **DR-01**, choose *Claims Platform* as the entity.
   Open **TM-07 Data security** and **TC-08 Work package and roadmap**.
6. As `user_library_admin`: **Insurance reference model > Views > + New view** OVP-01 with Capability and
   Value Stream; or copy VP-08 and change it. Own views are shown for every model. As `user_architect` the
   buttons are greyed out with the role needed.

## Checks

- `tests/sql/phase8_2_checks.sql` (as the API's login). Ends with "phase 8.2 checks passed".
- Earlier phases' checks still pass.
- `pytest services/api/tests`: `test_views.py` (views use ArchiMate 4 types, the demo estate keeps to the
  metamodel, the catalogue loads every view and audience, the tab is routed) and `test_reports.py` (every chart
  uses columns its dataset has, every report has audiences, the dependency report reads the chosen entity).

## Upgrading from phase 7

`.\eax clean-restart`. New API: `/api/v1/views`, `/api/v1/models/<model>/views[/<code>]`,
`/api/v1/models/<model>/maps/value-streams`, `/api/v1/models/<model>/maps/roadmap`, `/api/v1/report-audiences`.

## Not in phase 8.2

- Views drawn in draw.io from a view, and a report for every draw.io view (D148): phases 28 to 31.
- KPI tiles and trends over time (need snapshots): phase 24. Report designer: phase 24.
- Organisation map and information map as their own pages: the VP-01 Organization and VP-03 Information Structure
  views cover them for now.

## Test checklist (for the end-to-end testing phase, 36.1)

- [ ] Every VP dashboard opens with data for the demo estate; *Colour by* changes the heat map.
- [ ] The network, sankey, treemap and bubble charts draw (new chart types in 8.2, not tried before).
- [ ] DR-01: choose an entity and steps; DR-02: choose two types; DR-04: change the thresholds.
- [ ] Each audience dashboard shows its charts and the Model filter applies to all of them.
- [ ] Views tab: every view for several views; CSV downloads open in Excel.
- [ ] Own view: add, change, delete as a Library Admin; built-in ones cannot be changed.
- [ ] Value stream map and roadmap on the demo estate and on Fynbos Mutual.
