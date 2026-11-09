# What EA Explorer does today (version 0.15.1)

One page for anyone weighing EA Explorer up: what is **built and in the box today**, area by area, and what is still
**planned**, with its build phase. "Planned" adds to what is already there; it does not mean an area is missing.
Every phase in detail: [build-phases.md](build-phases.md). Decisions: [decisions.md](decisions.md).

| Area | Today |
| --- | --- |
| Cost and licence | Free and open source (AGPL-3.0); no charge per user, per object or per module. Self-hosted: one laptop, one server or your cloud |
| Metamodel and standards | ArchiMate 4 and the TOGAF 10 content metamodel built in; your own metamodels, edited, versioned, reviewed and pushed down to the models that use them |
| Diagrams and visual analysis | Over a dozen kinds of picture drawn from the repository itself, so they are never out of date; each opens in draw.io |
| Reports and BI | 30 standard reports and 49 viewpoints (each as diagram, catalogue, heat map, matrix and relationship list), roadmaps, value stream maps, gap, comparison and common analysis, quality dashboards; Apache Superset for your own |
| AI | An MCP server with 79 tools and 3 guided prompts: your own language model reads, analyses and builds, as you and with your permissions |
| Collaboration and governance | Private changes until committed, conflicts at commit, child models merged back, reviews and approvals, sign-off with a quorum, stakeholder acceptance of answers, a full change log |
| Projects (TOGAF ADM) | Architecture projects from 14 templates, the TOGAF 10 library (13 phases, 116 steps, 171 deliverables and artifacts), key questions, Business Model Canvases, the Architecture Repository |
| Documents and libraries | Document management (Mayan EDMS) inside projects, the reference library, the enterprise and project libraries with search |
| Integration | A REST API (OpenAPI), signed webhooks, Excel and CSV in and out with mappings, model packages, the MCP server |
| Operations | One command (`eax`) and a console, start-up in two tiers, health, tagged backups and restores, every service switchable |

## Cost and licence
- **AGPL-3.0, no licence fees**: every user, every model, every module. The open-source parts it uses are listed in
  [licences.md](licences.md).
- **Runs where you choose**: a laptop (Docker Desktop), one server, or your cloud; your database, your backups, your
  network. Nothing is sent anywhere unless you connect it.

## Metamodel and standards
Built:
- **ArchiMate 4** seeded in full, and **six EA Explorer extensions** for TOGAF business architecture (value stream
  stage, product lifecycle stage, business scenario, control, contract, measure), each marked as an extension (D345).
- **The TOGAF 10 content metamodel**, and the TOGAF catalogues, matrices and diagrams given by viewpoints (D345).
- **Your own metamodels**: layers, entity types, attributes, pick lists, allowed relationships and validation rules,
  edited in screens or as a whole document; a **lean metamodel** to start small.
- **Versions**: every metamodel change is a published version with its note and differences; compare any two;
  **push a new version down** to the models built on it, forced or offered (phase 8.1).
- **Reviews**: a metamodel draft (by a person or a language model) waits for review, comments and approval (D115, D130).
- **Industry reference models**: an insurance reference model to capability level 4, and the model library to share
  your own as reference models.

Planned: ArchiMate exchange format in and out, and a conformance check (phases 33, 33.1); more industry models (39).

## Diagrams and visual analysis
Built — every picture is **drawn from the repository when you open it**, so it always shows the data as it is now:
- **Network** around an entity (1 to 3 steps), **layers** (strategy to technology, for traceability), **impact**
  (what an entity leads to or depends on, up to 6 steps) and **split** (both ways at once).
- **Hierarchy and capability maps** (nested boxes, level 1 to 4), coloured by any attribute as a **heat map**.
- **Relationship matrices** between any two types.
- **Value stream maps** (stages with the capabilities enabling each, coloured by maturity or criticality) and
  **roadmaps** (plateaus, work packages and deliverables on a timeline).
- **Viewpoint diagrams** for all 49 viewpoints, and the **metamodel diagram**.
- **Business Model Canvases**, with differences between two shown in colour (D344).
- Click any box to open the entity. Every picture **opens in draw.io**, and saves as SVG, PNG or CSV.

Planned: **drawing in draw.io with the ArchiMate notation and writing the drawing back to the repository** (phases
28, 29, D288), and saved standard views (30, 31).

## Reports and BI
Built:
- **30 standard reports** and audience dashboards in Apache Superset, each checked; heat maps and a model overview.
- **49 viewpoints**, each shown five ways (diagram, catalogue, heat map, matrix, relationships), with the TOGAF
  artifact each gives (D345).
- **Roadmaps, value stream maps, dependency and impact** (phase 8.2).
- **Compare** any two models or tags; **TOGAF gap analysis** with resolutions and work packages; **common analysis**
  across many models (phases 8.3, 13.0.5).
- **Data quality**: score, completeness, freshness, orphans, rules, trends, drilling to the entities (phase 12).
- **Project reports** and the project's completeness by phase.
- **Your own reports**: every entity type is a report view, so Superset (charts, dashboards, SQL) works on it directly.

Planned: report trends, schedules, feeds and a report designer in the screens (phase 24).

## AI (bring your own model)
Built ([mcp.md](mcp.md)):
- **An MCP server** at `/mcp`, with **79 tools** and **3 guided prompts** (build a project, build a model, fill a
  model). Any model that speaks MCP works: hosted or local. None is shipped and nothing is sent to one unless you
  connect it.
- It works **as the person signed in**, with exactly their permissions.
- It **reads and analyses**: metamodels, entities, relationships, history at any point in time, paths and impact,
  search, viewpoints, value streams, roadmaps, comparisons, gap analyses, quality findings.
- It **builds**: models (empty, copies, children), entities and relationships in bulk, projects from templates,
  steps, documents' acceptance, key questions and their answers, Business Model Canvases.
- It **proposes, a person decides**: what it adds is the person's uncommitted change until committed; metamodel
  drafts and quality rules wait for review.

Planned: proposals into a staging area across the whole repository (phases 26, 27).

## Collaboration and governance
Built:
- **Roles and permissions** through Keycloak (single sign-on), global and per model and per project.
- **People's skills**: each user adds their own on My profile; the Skills repository lists every user with theirs (D353).
- **Commits**: changes are private until committed; conflicts are shown at commit; roll back; Committer and History
  Viewer roles (phase 8).
- **Child models and merge back** (work in a copy, merge it into its parent), split and merge models (phases 8, 13.0.4).
- **Tags**: frozen snapshots to compare with, copy from or go back to.
- **Reviews and approvals**: metamodel drafts, quality rules, documents (approval by the sign-off people, with a
  quorum), the governance log (dispensations and decisions, with approval), project sign-off (D321).
- **Key questions**: each stakeholder question answered with links to the artifacts and accepted by the stakeholder (D341, D342).
- **Collecting data from people**: send stakeholders a sheet for their part of a model; review what comes back (WIZ-018).
- **Notifications and requests** (like tickets) between people, and **signed webhooks** to other systems (phase 8.1).
- **The change log**: every action, who, when, before and after; in its own database (phase 9).
- **Guided wizards** for the common jobs (phase 16.3).

Planned: work copies and merge back across a whole project (phases 19, 20), dedupe (21), ownership and
collaboration (22), portfolio, lifecycle and impact (23), surveys (38.1).

## Projects (TOGAF ADM)
Built (phase 13):
- **Architecture projects** from **14 templates** (transformation, as-is documentation, build or buy, cloud migration,
  acquisition and others), each with its models in roles (current, target, transition, scenario, reference, working copy).
- **The TOGAF 10 library**: 13 phases, 116 steps, 171 deliverables and artifacts, 51 repository folders.
- Scope, goals and outcomes, stakeholders and their map, **key questions**, principles, standards, the governance
  log, the charter, calendars and the Architecture Board, tracking sheets, tasks, sign-off.
- **The Architecture Repository**, the content framework and the standards information base.
- **Business architecture**: the TOGAF Phase B artifacts with their viewpoints, and **Business Model Canvases**
  (current, target, working copies marked by hand, compare and make a new one) (D344, D345).
- **Project backups and restores**, with the project's documents, models and library.

## Documents and libraries
Built:
- **Document management** (Mayan EDMS) inside each project's repository: versions, check-out, tags, acceptance,
  approval, archive.
- **The reference library**: standards, regulations and research, with search inside the documents (D300).
- **The enterprise library and project libraries**: simple pages, links into EA Explorer and the web, the odd file,
  one search box, history and undo; or point it at your own intranet instead (phase 15.2, D346 to D351).

## Integration
Built:
- **A REST API** for everything the screens do, documented with OpenAPI at `/api/docs`.
- **Signed webhooks** for what happens in EA Explorer (phase 8.1).
- **Excel and CSV**: sheets built for the types you choose (with drop-downs), loaded with a preview, column mappings
  and undo (phase 10.1); tracking sheets in and out (13.2).
- **Model packages** to move models between installations (phase 4).
- **The MCP server**, so assistants can connect EA Explorer to whatever else they reach.

Planned: collection from other systems, a CMDB and cloud inventories with reconciliation, ETL and outbound feeds
(phases 34, 34.1).

## Operations
Built ([operations.md](operations.md), [command-line-and-console.md](command-line-and-console.md)):
- **One command**, `eax`, for Windows, Linux and macOS: start, stop, status, logs, health, backup, restore, services,
  passwords; and **`eax console`**, a menu for getting EA Explorer back up.
- **Start-up in two tiers**: people can sign in within a minute or two while the rest comes up.
- **Health** of every part in the header and on Heartbeat; the administration console with settings applied at once.
- **Backups**: tagged infrastructure backups (every database, files, certificate, configuration, versions), nightly
  and on demand, pinned, restored whole or in part; application backups of every model; project backups.
- **Every optional service can be switched off** (reports, documents, draw.io, MCP, change log, backups, library),
  with a dated copy of the configuration kept.

Planned: deployment kinds and scripts, upgrades, test automation, scale-out ([story-load-balancing.md](story-load-balancing.md))
and real-time mirrors ([story-real-time-mirrors.md](story-real-time-mirrors.md)) (phases 35 to 37).
