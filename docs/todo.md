# To do

Open items that are not part of a build phase yet, or are waiting on a test or a decision.
Tick an item (`[x]`) when it is done; remove it at the next tidy-up.

## Waiting on a test (Gaurav)

- [x] **Accept phase 1** (accepted 4 Nov 2026).
- [x] **Accept phase 2** (accepted 4 Nov 2026; checks passed, MCP tried from Claude Code).
- [x] **Phase 2 closed** (4 Nov 2026, version 0.2.1).
- [x] **Role and permission model agreed** (4 Nov 2026, D58-D63): see the Roles sheet of the requirements
  workbook and phase 3.1 in the plan. Settled 4 Nov: only Model Admins change the metamodel (D89);
  Model Admins also edit and commit content (D90).

## Phase 3 (version 0.3.0)

- [x] **SQL window read-only** (D52): *Allow changes* removed; every run is rolled back.
- [x] **Phase 3 accepted** (4 Nov 2026). Was: test phase 3 (Gaurav): `.\eax clean-run`, the demo and checks in [phase-3.md](phase-3.md).

## Phase 3.1 (version 0.3.1)

- [x] **Phase 3.1 accepted** (4 Nov 2026). Was: test phase 3.1 (Gaurav): `.\eax clean-run`, the demo and checks in [phase-3.1.md](phase-3.1.md).
- [x] Superset reports by model (phase 5, D138). Mayan cabinets by model (phase 13), as planned.

## Phase 5 (version 0.5.0)

- [x] **Phase 5 accepted and closed** (4 Nov 2026, D143): the reports basically work.
- [ ] **Check each of the 32 report dashboards** in the testing phase 36.1 (D143), with the checklist in [phase-5.md](phase-5.md).

## Phase 6 (version 0.6.0)

- [x] **Phase 6 accepted and closed** (4 Nov 2026, D146); end-to-end test in phase 36.1.
- [x] **Plan reviewed** (4 Nov 2026, D147): 7, 8 (with 38.2), 8.2 reports and views, 8.3 model tags, 8.4 backups, 9, 10, 10.1 import sheets, then the rest.

## Phase 7 (version 0.7.0)

- [x] **Test phase 7** (accepted 4 Nov 2026, D157; end-to-end test in 36.1): `.\eax clean-restart`, the demo and checks in [phase-7.md](phase-7.md).
- [x] **Test phase 8.2** (accepted 5 Nov 2026, D164; each report checked in 36.1): `.\eax clean-restart`, the demo and checks in [phase-8.2.md](phase-8.2.md). The Superset charts new in 8.2 (network, sankey, treemap, bubble) could not be tried here: check they draw.
- [x] **Test phase 8** (accepted 5 Nov 2026, D171; end-to-end test in 36.1) (0.8.3): `.\eax clean-restart`, the demo and checks in [phase-8.md](phase-8.md). New test users `user_committer` and `user_history_viewer` (same password as the others).
- [ ] **Test phase 8.3** (0.8.4): `.\eax clean-restart`, the demo and checks in [phase-8.3.md](phase-8.3.md).
- [ ] **Test phase 9** (0.9.0), with 8.3: `.\eax clean-restart`, the demo and checks in [phase-9.md](phase-9.md).
- [ ] **Test phase 10** (0.10.0), with 8.3 and 9: the demo and checks in [phase-10.md](phase-10.md).
- [ ] **Test phase 10.1** (0.10.1): the demo and checks in [phase-10.1.md](phase-10.1.md); open the .xlsm in Excel.
- [ ] **Design discussion for draw.io (web), phases 28 and 29** (D174): before building, agree how draw.io connects to a model, the stencil of entity and relationship types, harvest and saves. The desktop app is not supported.
- [ ] **Phase 28-29 rule (D167)**: draw.io diagram saves go through `POST /models/<model>/changes/batch`, so they are committed like every other change.
- [ ] **Phase 10: clean up the start page (owner, 5 Nov 2026, D163). Discuss with the owner first, then build.** It has grown into a list of build features
  (Grid, Data entry...) that mean little to a user. Rework it with the home dashboard: start from what a person wants
  to do (my models, my favourites and recent items, find something, my reports and dashboards for my audience,
  things waiting for me), and move the "what is coming" cards to an About or roadmap page.
- [ ] Phase 10: application settings on the admin screen: currency (USD), location and time zone, formats, financial year (D156).
- [ ] Phase 8: person-based change log, My changes and the View change history permission (D151).
- [ ] **Phase 8 design inputs (owner, 5 Nov 2026, D165)**, being settled question by question:
  1. Content (data only, not the metamodel) entered in a model is private to the person who entered it until it is
     committed; no one else sees it. A new role may commit. Only committed data is in the version history.
  2. A changes page shows every uncommitted change: commit, reject or roll back, a whole change set or row by row.
  3. Model Admins and Model Sub Admins can also commit.
  4. From that page a person either commits (if they have the commit role) or raises a request for commit. Nothing
     is committed automatically.
  5. Draft models: every model creation (new, copy, child, upload) starts as a draft and is approved or rejected,
     even when the person could approve it; people may approve or reject their own drafts.
  6. Upload a model (Excel or zip) into an existing or draft model and merge it: entities, attributes and
     relationships of the other model added or updated, with merge management and conflict resolution.
  Answers (5 Nov 2026): Committer is a **model role** (People tab). Uncommitted changes are seen **only by the person
  who made them, and by the model's committers once a request for commit is raised**. Two people changing the same
  entity: the **conflict is shown at commit** (keep committed, take theirs, or merge field by field). **Roll back**
  covers both: discard uncommitted changes (whole set or row) and undo a committed commit (whole or row) as a new
  commit. A request for commit goes to **all the model's Committers, Model Admins and Sub Admins**, any of whom can
  commit, reject or send it back with a note. **Draft models** are approved or rejected by the creator, Super Admins,
  the Model Admins of the model a child merges into, and Library Admins for library models; while a draft, people
  with roles can **work in it but it is hidden** from the model list, library and reports. **Merge upload**: entities
  matched by **type and name**; every conflict listed and **decided one by one** (keep mine, take theirs, type a
  value, or all mine or all theirs); types, attributes and relationship types the target lacks are **offered to a
  Model Admin to add** (one new metamodel version) or left out; the merged content becomes **one uncommitted change
  set** that goes through commit.
- [ ] **Production upgrades keep the data (D162, at production deployment, phase 36)**: keep a database upgrade script for
  every version, match the database's version to the release and run the scripts in order; take a backup before every
  upgrade (and refuse to upgrade without one); in production the clean restart is switched off by a setting in the
  .env file, and someone has to change that setting on purpose to allow a clean start there. Clean restarts stay the
  rule in development.

## Phase 14, backup and restore (owner, 4 Nov 2026)

- [ ] **On-demand backups** from the web (IT Admin, Super Admin), **on-demand restores** (of a chosen backup, with
  a confirmation and a backup taken first) and **scheduled backups** whose schedule and retention are set on
  screen (today a fixed nightly backup at 2 am from the config file). Restore works from the web screens
  **and from a backup file at a location the person browses to and gives** (a backup from another
  installation, a share, a downloaded file). In phase 14 as planned; to cover in the discussion after phase 6.

## Model tags (owner, 4 Nov 2026): phase to settle in the discussion after phase 6

- [ ] **Tag a whole model with all its data**, like a git tag: a named, read-only point in time of the model's
  metamodel and content. Roll the model back to a tag; compare a model with itself at a tag (gaps within a
  model), two tags of one model, two models at their tags, and a model with its parent at tags. Builds on
  the full history kept for every row (and deep copies keep it, D132) and origin guids for matching (D133).
  Closest planned phase: 24.1 (model versions, comparison and gap analysis, D111), which may move earlier.

## Richer reports (owner, 4 Nov 2026): for the discussion after phase 6

- [ ] **Reports and dashboards by audience** (owner, 4 Nov 2026, D153; phase 8.2). An audience is the kind of person
  a report interests (CEO, CFO, architect...). Audiences are **not** roles in the system and give no access:
  model access still decides what anyone sees. Reports and dashboards are grouped by audience, one report can
  serve several audiences, and each audience gets its own dashboard. Every new report is given its audiences.
  Draft audiences (to confirm in 8.2):
  - *Executive*: CEO, CFO, CIO, CTO, COO, Chief Risk Officer (CRO), Chief Information Security Officer
    (CISO), Chief Data Officer, Chief Compliance Officer.
  - *Business*: Business unit head, Product owner, Process owner, Change manager, Portfolio manager (PMO).
  - *Architecture*: Enterprise architect, Business architect, Solution architect, Application architect,
    Data architect, Technology architect, Integration architect, Security architect, Architecture board.
  - *Operations and control*: Application owner, IT operations, Procurement and vendor manager, Internal
    audit, Model owner, Data steward.
  Draft distribution of the thirty standard reports:

  | Report | Title | Audiences |
  |---|---|---|
  | SR-01 | Application portfolio inventory | CIO, Application architect, Application owner, Portfolio manager |
  | SR-02 | Business capability catalogue | CEO, COO, Business architect, Business unit head |
  | SR-03 | Technology component inventory | CTO, Technology architect, IT operations |
  | SR-04 | Data entity catalogue | Chief Data Officer, Data architect |
  | SR-05 | Business process catalogue | COO, Process owner, Business architect |
  | SR-06 | Interface and integration catalogue | Integration architect, Solution architect, IT operations |
  | SR-07 | Stakeholder and actor catalogue | Enterprise architect, Change manager |
  | SR-08 | Motivation catalogue | CEO, Architecture board, Enterprise architect |
  | SR-09 | Application against capability | CIO, Business architect, Application architect |
  | SR-10 | Application against process | COO, Process owner, Application owner |
  | SR-11 | Application against data entity (CRUD) | Chief Data Officer, Data architect, CISO |
  | SR-12 | Application against technology | CTO, Technology architect, Application architect |
  | SR-13 | Process against role | COO, Process owner |
  | SR-14 | Capability against value stream | CEO, COO, Business architect, Product owner |
  | SR-15 | Application interaction matrix | Integration architect, Solution architect |
  | SR-16 | Capability heatmap | CEO, CIO, COO, Business architect |
  | SR-17 | Technology lifecycle and end-of-life | CTO, CRO, Technology architect, IT operations |
  | SR-18 | Application TIME quadrant | CIO, CFO, Portfolio manager |
  | SR-19 | Criticality against technical health | CIO, CTO, Portfolio manager |
  | SR-20 | Cost by capability | CFO, CEO, CIO |
  | SR-21 | Vendor concentration | CFO, Procurement and vendor manager, CRO |
  | SR-22 | Impact analysis | Solution architect, Change manager, Enterprise architect |
  | SR-23 | Obsolescence risk | CRO, CTO, CISO, Internal audit |
  | SR-24 | Single points of failure | CRO, CTO, IT operations |
  | SR-25 | Rationalisation candidates | CIO, CFO, Portfolio manager |
  | SR-26 | Completeness by type and owner | Model owner, Enterprise architect |
  | SR-27 | Orphans and missing relationships | Model owner, Data steward |
  | SR-28 | Duplicate candidates | Model owner, Data steward |
  | SR-29 | Change activity | Architecture board, Internal audit, Model owner |
  | SR-30 | Version and baseline comparison | Enterprise architect, Architecture board |

- [ ] The standard reports are mostly tables and pivots; the owner wants more impressive reports. Market review
  (source "Market review", D114) found 19 report types to add. In Superset: bubble portfolio with TIME quadrants,
  capability treemap or sunburst coloured by a KPI, integration graph and data-flow sankey, KPI tiles with trends
  (needs snapshots), world map, maturity spider, cost waterfall, calendar heatmap, obsolescence projection,
  persona dashboards. As EA Explorer pages: nested capability landscape with applications inside, coloured by a
  switchable attribute; items-in-cells matrix; lifecycle and transformation roadmap (Gantt); impact and
  traceability explorer; technology radar. With switchable colouring, click-through to the entity, hover
  highlighting, drill-down, a time slider (model tags) and saved views.

## Open Group reports and views (owner, 4 Nov 2026): for the discussion after phase 6

- [ ] Follow the Open Group: the TOGAF 10 catalogs, matrices and diagrams by ADM phase, the 25 ArchiMate 4 example
  viewpoints (basic, motivation, strategy, implementation and migration) and the business architecture maps (capability
  map heat-mapped by maturity, importance, investment or risk; value stream map; value stream x capability with heat;
  organisation map; information map; strategy to capability tracing). Gaps found against the 30 standard reports:
  principles, stakeholder map, contract/measure, location and glossary catalogs; strategy/capability,
  capability/organisation, data entity/function, data security, role/application, application/organisation matrices;
  value stream map, organisation map, information map, business footprint, decompositions, conceptual/logical data,
  data dissemination and lifecycle, application communication, application and user location, service realisation and
  layered views, environments and platform decomposition, technology standards, project context, benefits, migration
  and implementation and migration, outcome realisation, resource map, requirements realisation. Diagram-type views
  overlap with the standard views (phases 30-31, draw.io); the catalogs and matrices are Superset reports.
- [ ] Checked against the ArchiMate 4 Specification (owner's copy, 4 Nov 2026): Appendix C has 25 example viewpoints
  (13 basic in four categories: composition, support, cooperation, realization; 4 motivation; 5 strategy; 3
  implementation and migration), each with stakeholders, concerns, purpose, scope and the element types it allows
  (grouping and junctions in all; Layered allows every core element). Section 13.4: a viewpoint's representation may
  be a diagram, a catalog, a matrix or another visualisation, and attribute profiles can colour views as heat maps.
  Our ArchiMate 4 template matches the 3.2 to 4 changes (Appendix E.4). Idea: viewpoints as data (element types per
  viewpoint) so any model can be shown through any viewpoint as a diagram, catalog, matrix or heat map.

## Deployment (to discuss when we reach the deployment phase)

- [ ] **Publish the EA Explorer images on Docker Hub** (api, web, superset, backup) so an installation can pull
  them instead of building. How to build and push (GitHub Actions on a version tag, an eax command, or
  both), the namespace and the tags are to be discussed then (owner, 4 Nov 2026).

## Decisions waiting before their phase

- [x] Import, export and survey sheets: both Excel and CSV (D88).
- [x] Retiring an entity type makes its entities read-only until it is restored (D87, built in 0.3.0).
- [x] **ETL tool for the integration phase (34.1, D91)**: Apache Hop (D128). The connectors needed are
  settled in that phase's design session.
- [ ] **Kinds of notification and request (8.1, D83)**: to agree in that phase's design session.

## Design session before phase 15 (architecture projects and repository, D103-D105)

- Projects and models: several projects on one model, or a project on a copy merged back. What happens to a project's content when
  the project closes, is merged or is abandoned? Can one project work on more than one model?
- Which registers are organisation-wide and which per project, beyond those in D104 (risks? standards waivers?).
- The ADM framework definition: TOGAF 10 phases and deliverables shipped; how an organisation adds its own; gates and who approves.
- Artefact templates: which ones ship (the TOGAF sample content in the project files is a good start), and how a catalogue,
  matrix or view is generated into a workbook or document.
- Review and approval: how it uses the actions, alerts and workflows of phase 8.1 and the commits of phase 8.
- Roles on a project (do they flow to its models, or stay separate from model roles?).
- **Project workflow wizard** (owner, 5 Nov 2026, D160): one guided path through a project, steps to confirm:
  1. Create the project (purpose, scope, sponsor, people).
  2. Choose a model or create one (from the core model or a copy, with lineage).
  3. Set up documents and templates (setup pack, starter documents in Mayan, starter diagrams and reports).
  4. Plan the ADM: which phases, in what order, **several running at the same time**, each with deliverables,
     owners, dates and a gate.
  5. Run the phases: work the deliverables, produce artefacts from templates, review and approve them.
  6. Track governance: decisions, compliance reviews, dispensations, risks, issues, change requests and
     requirements, with dashboards.
  7. Gate reviews and phase sign-off.
  8. Implementation governance (Phase G): Architecture Contracts and compliance reviews of delivery projects.
  9. Change management (Phase H): change requests, and starting a new iteration or project.
  10. Close the project: what happens to its content, the final deliverables, lessons learned.
  To settle: whether the wizard is a step-by-step screen, a project cockpit with a checklist, or both; who may
  skip steps; whether the steps come from the framework definition so an organisation can change them.

## Design session before phase 24.1 (model versions, comparison and gap analysis, D111)

- What counts as a change: which fields, attributes and relationship types; how to treat renames, moves in a hierarchy, retired
  versus deleted, and values that differ only in format (dates, numbers, case, whitespace).
- Matching across models: origin (copied from), display ID, type and name; how manual matches are kept; what to do with
  one-to-many matches (one application split into two).
- Comparison profiles: which ship (application portfolio, capabilities, technology), who may save shared ones.
- Version storage: full snapshots, or history replayed to a point; size and speed on large models.
- Gap analysis: the matrix layout (TOGAF baseline by target), what a gap carries (note, resolution, work package), and the gap
  report's Word and Excel layouts.

## Phase 4 questions (answered 4 Nov 2026)

- [x] Package format: zip with JSON and CSV, and an Excel workbook too (D116).
- [x] Pack files: built with Mayan in phase 13 (D117).
- [x] Who curates the library: a new Library Admin role (D118).
- [x] Own roots as library models: yes, as roots of their own (D119).
- [x] AI drafting: step-by-step and whole-file tools, the person chooses; same rights as editing by hand (D120).
- [x] New framework versions: copy with mapping or upgrade in place, Model Admin chooses; delete: Super Admin, refused
  while others depend (D121).

## Waiting on input (Gaurav)

- [ ] **Repository set-up files** for project setup (PRJ-004, build phase 16.1): share the files
  that define a project's repository structure and starter material.

## Platform follow-ups (from phase 0)

- [ ] Pin the Mayan image (`mayanedms/mayanedms:s4`, ran as 4.12.2) and the other images by digest
  once the checklist passes.
- [ ] Confirm Mayan document upload and OCR jobs run with `dms-broker` (Valkey) as its only broker.
- [ ] Single sign-out: after signing out of the start page, Superset asks to sign in again.
- [ ] draw.io embed mode when self-hosted: prove before phase 28.
- [ ] Superset row filtering by model: needed from phase 5.

## Productionising stories (discuss before the final deployment scripts, phase 36)

Noted 4 Nov 2026 (D99). To discuss and settle when we build the final deployment scripts:

- [ ] **Scale-out**: run the API, job runner, reports and documents on several servers behind a load
  balancer; database and storage sized and placed for production.
- [ ] **Users on another platform**: keep the people and roles in an existing identity platform
  rather than only in our Keycloak (Keycloak federating to it, or replaced by it).
- [ ] **Integrated AD-based sign-in**: Active Directory through Keycloak, with AD groups mapped to
  Keycloak roles in Keycloak (D93); brings back SEC-003, which is "not planned now" (D73).
- [ ] **Sign-in and paths in the config file**: choose the identity providers and sign-in settings,
  and the folders and storage paths (data, backups, imports, exports, documents), in the config file
  for each deployment.
- [ ] **A key vault for secrets**: database passwords, client secrets, the break-glass password and
  every other password held in a vault (for example HashiCorp Vault, Azure Key Vault or AWS Secrets
  Manager) instead of the config file; containers read them at start.

- [ ] **End-to-end testing of phase 4 onwards** (D129): deferred to phase 36.1; the checklist is in
  docs/phase-4.md and each later phase adds its own.

- [ ] **Drafts, approvals and publishing** (D135): design session and stories in phase 38.2. Known gap: a
  Model Admin of a draft's source model cannot see the requested draft to approve it.

## Backlog (to work out later)

- **Similarity (fuzzy) matching in Compare and gap analyses** (owner, 5 Nov 2026: not now, keep in the plan; D178). An extra
  matching step after the exact ones, among still unmatched elements of the same entity type, on tidied names (case,
  punctuation, filler words such as "system" or "platform"), with a threshold on the filter screen. To decide when it is
  taken up: suggested and confirmed by a person, or automatic and marked with its score. Goes with the screen for
  hand-made matches (phase 19).

- [ ] **Enterprise readiness: what needs improving** (owner, 4 Nov 2026, D158). From the review of whether EA
  Explorer is enterprise-scale and how it compares with free and paid tools. **Now in the plan (D159):** phase
  8.5 (F9, F10, F11, F12, F14) and phase 36.2 (F1 to F8, F13, F15 to F20).
  - *Trust and security*
    - F1 Penetration test and security review before any bank or insurer uses it (reconsider D56) (37).
    - F2 Dependency and container image scanning on every build; patch policy for the open-source
      products inside (36).
    - F3 Encryption at rest for the database, documents and backups; secrets in a key vault (36).
    - F4 Tamper-evident audit log (entries chained or signed, kept read-only, exported to a log store) (25).
    - F5 Rate limits and abuse protection per user and per token on the API and MCP (25).
  - *Scale and availability*
    - F6 Scale test with a large model and many users (backlog D5), with response-time targets for grids,
      search, reports, copies and imports, and fixes for what is slow (37).
    - F7 High availability: database replica and failover, more than one API and web container, no single
      point of failure (36).
    - F8 Disaster recovery: stated recovery point and recovery time, a tested restore drill, backups kept
      off the server (8.4 and 36).
    - F9 Monitoring and alerting: metrics, logs and alerts to the operations team (35).
  - *Upgrades and releases*
    - F10 Upgrades that keep the data: every new version upgrades a running installation in place
      (migrations only, no clean restart), tested from each released version (36).
    - F11 Release process: continuous integration running every check and test, versioned releases,
      release notes, a supported-versions policy (36.1 and 37).
    - F12 Raise automated test coverage across API, database and screens, so changes do not break earlier
      phases (36.1).
  - *Quality of what users see*
    - F13 Reports good enough for executives (owner: today's reports are not): every report checked and
      redesigned (8.2 and 36.1).
    - F14 Superset set-up and report import tested on a real installation end to end (8.2).
    - F15 Usability: consistent screens, fewer clicks for common tasks, a usability test with real
      architects, accessibility to WCAG 2.1 AA (37).
    - F16 Diagramming depth: drawing with model elements as smooth as a desktop modelling tool (28 and 29).
    - F17 Content: reference models and starter packs good enough to start with on day one (39).
  - *Enterprise identity*
    - F18 Active Directory and other identity providers, group-to-role mapping (25 and 36).
  - *Product and continuity*
    - F19 Decide who the product is for (suggested: consultancies and mid-to-large financial-services
      organisations wanting a self-hosted, ArchiMate 4, AI-first repository) and choose backlog items that
      sharpen that, rather than everything other tools have.
    - F20 Continuity: more than one maintainer, contributor guide, architecture documentation for
      developers, and a support model (who answers when it breaks).

- [ ] **Market review of open-source EA tools** (owner, 4 Nov 2026, D154): features found that the plan and the
  backlog above do not yet have. Phases to be set; the phase in brackets is only a suggestion.
  - *Process and delivery*
    - E1 Process modelling (BPMN 2.0): a process editor and viewer in the browser; process versions (draft,
      published, archived) with approval; process steps linked to entities (applications, data, roles);
      process maturity assessments (efficiency, effectiveness, compliance, automation, 1 to 5) with
      actions and history; process map, process x capability, process x application reports (16.3).
    - E2 Initiatives and delivery portfolio: initiatives with a Gantt overview and health; periodic
      status reports (schedule, cost, scope: on track, at risk, off track); work breakdown with
      milestones and roll-up; a task board (to do, doing, done, blocked); capex and opex budget lines by
      financial year against actuals; initiative risks with a probability x impact matrix (16.3, with
      roadmaps A1).
    - E3 Benefits and value tracking: expected and realised value of initiatives and architecture work
      over time (23.1).
  - *Data quality and governance*
    - E4 Approval state per entity: draft, approved, rejected, and "approval broken" when a substantive
      field changes after approval; shown on the entity and in reports (8).
    - E5 Quality score per entity (0 to 100%) weighted by field importance set in the metamodel, plus
      stale entities (not reviewed for N months) (12).
    - E6 Stakeholders per entity with roles the organisation defines (owner, steward, SME, accountable,
      consulted...), driving notifications, surveys and tasks (22).
    - E7 Tag groups: tags in named groups, single or multi select, mandatory per entity type (12).
    - E8 Form layout designer: drag sections and fields on an entity type's form (10).
    - E9 Automations: rules of the form "when this happens and this is true, do that" (notify, set a
      value, create a task, start a survey) without code (8.1).
  - *Reports*
    - E10 Time slider on reports: any report as it was on a past date, and with effective dates (A2) as
      it will be (8.2 with 9).
    - E11 Print and PDF layout for every report and page (8.2).
    - E12 Matrix reports with grouped, collapsible hierarchy headers on both axes (8.2).
    - E13 Process and project reports from E1 and E2 (8.2 once those exist).
  - *AI (adds to C1)*
    - E14 Description suggestions: draft an entity's description from public web sources, with the
      sources and a confidence, for chosen entity types; a local or a hosted model (27.1).
    - E15 Vendor normalisation: one canonical vendor list and hierarchy from messy vendor names (27.1).
    - E16 Modernisation assessment: effort, priority and recommendation per application (27.1).
    - E17 Target-architecture wizard: from a goal to a draft target architecture, a layered dependency
      view, an initiative and a draft decision record, all as proposals into staging (27.1 with 27).
    - E18 Regulatory scans: check the model against POPIA, the Prudential Authority and other sector rules,
      ISO 27001, and others chosen; findings become risks in the register (A5) (27.1).
  - *Integration and exchange*
    - E19 End-of-life feed: link technology entities to a public end-of-life data source (for example
      endoflife.date) with fuzzy matching and bulk linking, keeping end-of-life dates current (34).
    - E20 ServiceNow CMDB two-way sync with field mapping, direction per field and staged review (34).
    - E21 Cloud and tool extractors: AWS, Azure, Confluence, Jira into staging (34.1).
    - E22 Jira task sync and Slack notifications, beside Teams and email (B3) (34).
    - E23 Import preview: a change-by-change difference (new, changed, removed) before any import or
      exchange file is applied (10.1 and 33).
    - E24 Architecture as code: export and import a model as readable YAML files kept in Git, a lint
      command for pipelines (types, relationships, references), and sync from a Git repository (33).
    - E25 Command-line tool: import, export, lint, run reports and analysis scripts from a terminal or a
      pipeline, using API tokens (D2) (33).
    - E26 Scripting: run scripts (Python) against a model in a sandbox for bulk analysis and changes, the
      changes going into staging (27).
    - E27 Static HTML export: a whole model as an offline, browsable website (zip) to send to people
      outside the tool (24.2 with the portal B2).
  - *Diagrams*
    - E28 Specialisation icons and label expressions on draw.io shapes (a shape's label built from
      attributes, for example name and lifecycle) (28).
    - E29 Free-form sketch and canvas pages (whiteboard) beside the ArchiMate views (29).
  - *Platform*
    - E30 Interface in several languages (English first; for example Afrikaans, isiZulu, French,
      Portuguese, German, Spanish) (37).
    - E31 Custom roles made from the product's permissions, beyond the agreed roles (25).
    - E32 Kubernetes Helm chart and Terraform scripts; images for amd64 and arm64, signed, with a
      software bill of materials (36).
    - E33 Move a model or the whole installation to another installation in one step (8.4 with backups).
    - E34 Extension store: add-ons installed from the admin screens (assessments, value tracker, register
      packs such as an operational resilience register) (with D6, after 1.0).
    - E35 Currency settings: the base currency is USD (owner, 4 Nov 2026); other currencies (for example ZAR)
      with exchange rates for cost attributes, converted to USD in reports (23.1).
    - E37 Live updates (agreed by the owner, 4 Nov 2026): open pages and grids refresh, or warn, when someone
      else changes the same data (8).

- [ ] **Product gap review** (owner, 4 Nov 2026, D152): added to the backlog, phases to be set. The phase in
  brackets is only a suggestion.
  - *Planning content*
    - A1 Roadmaps and transition architectures: baseline, transition and target plateaus, gaps and work
      packages, a timeline or Gantt roadmap from the model (16.3).
    - A2 Effective dates: valid-from and valid-to on entities and relationships; see the architecture as it
      will be on any date (16.3).
    - A3 Scenarios and options: branch a target state into options and compare cost, risk and impact (16.3;
      joins the what-if item below).
    - A4 Cost and investment: cost per application, roll-ups to capabilities, value streams and
      organisations, run and change spend, simple business cases (23.1).
    - A5 Risk, controls and compliance: regulatory obligation register (POPIA, sector regulators), controls
      mapped to applications, data and processes, risk ratings, compliance gap reports (23.2).
    - A6 Computed attributes and roll-ups: formulas, values inherited from parents, aggregates over
      children such as capability health from its applications (8.5).
    - A7 Technology radar and standards lifecycle: adopt, trial, hold, retire; end-of-life dates driving
      obsolescence alerts (23.2).
  - *Producing and sharing*
    - B1 Document generation: Word, PDF and PowerPoint deliverables (Architecture Definition Document,
      Statement of Architecture Work, catalogues) from templates filled with live model data (16.4).
    - B2 Published read-only portal: browse and search an approved model without a role in the tool (24.2).
    - B3 Notifications to Microsoft Teams and email (10.2).
    - B4 Help, guided tours and onboarding inside the product (10.2; joins the documentation item below).
    - B5 Phone and tablet layout: read-only browsing and approvals (10.2).
  - *Intelligence*
    - C1 In-app AI assistant: ask the model questions in the tool; suggestions for missing relationships,
      descriptions, classifications, duplicates and rule fixes; draft artefacts from model data (27.1).
  - *Platform and governance*
    - D1 Several organisations in one installation, each with its own admins, users, branding and data (25.2;
      only if wanted).
    - D2 API tokens and service accounts: long-lived, scoped, for scripts, ETL and integrations (25.1).
    - D3 Personal data and POPIA: find and export one person's data, anonymise people who leave,
      retention rules (25.1).
    - D4 Archive and purge: archive whole models read-only, purge after a retention period (25.1).
    - D5 Scale and performance test: a large model (for example 100,000 entities, 500,000 relationships)
      through grids, search, reports and copies (37).
    - D6 Extensions: custom pages, widgets and report types without changing core code (after 1.0).

- [ ] **What-if analysis in the reports phase** (asked 4 Nov 2026): explore the effect of a change before
  making it (for example retiring an application: which capabilities, processes and projects lose
  support). Either built into the reports (scenarios over a copy or a baseline of the model) or done
  through a language model over the MCP tools, or both. To decide before the reports phases (5, 11).

- [ ] **Full documentation, guidebooks and inline help** (asked 4 Nov 2026, D126; to build later, phase to be
  set). Three parts:
  - *Full documentation*: a documentation site published with every version, covering every screen,
    concept (models, metamodels, roots, library, child and independent models, packages, drafts),
    role and permission, the REST API, the MCP tools, operations and upgrades.
  - *Guidebooks*: step-by-step guides per role and per task (first model, building a root metamodel,
    sharing a library model, testing an upload, drafting a metamodel with AI, giving people roles),
    with screenshots, downloadable as PDF.
  - *Inline help*: a help panel on every screen (what it is, what you can do there, what your roles
    allow), help for every field from the metamodel's own help text, a "?" beside each section that
    opens the matching guide page, and search across the help from the top bar. Builds on the tooltips
    and greyed-out controls of phase 4 (D123, D125).
  To settle: the documentation tool (kept in the repository and built with the product), whether the
  help is per version, and how the industry guides of phase 39 fit in.

## Later (already in the requirements)

- MCP as a remote connector for claude.ai and Claude Desktop custom connectors: public https and
  Keycloak OAuth on server installations (AI-011, phase 26).
