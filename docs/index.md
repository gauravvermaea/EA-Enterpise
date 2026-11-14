# Documentation

Every document of EA Explorer, in one place. Start with the [README](../README.md): what EA Explorer is, the quick start,
the `eax` commands (backups and restores included) and the phase table.

## Running it

| Document | What it covers |
| --- | --- |
| [README](../README.md) | Quick start on a laptop, the `eax` commands, the work folder, certificates, the phase table |
| [Drawn views in draw.io (design)](phase-28.md) | Phases 28 and 29: views drawn in draw.io from the model's own entities, the rules, where views live, entity type looks (D354, D355) |
| [What EA Explorer does today](capabilities.md) | Every area (metamodel, diagrams, reports, AI, governance, projects, documents, integration, operations): what is built today and what is planned, with its phase |
| [Business architecture artifacts](business-architecture.md) | The TOGAF Phase B catalogues, matrices and diagrams as views, the extension types they need, the Business views tab of a model and the Business artifacts tab of a project (D345, D352) |
| [Business Model Canvas](business-model-canvas.md) | A project's canvases: current, target, working copies and scenarios; compare, clean up, export (D344) |
| [Key questions and placeholder views](key-questions.md) | The questions a project's work answers: views mapped to each, placeholders where none fits, the answer (rich text with links to the artifacts) and the stakeholder's acceptance (D341, D342) |
| [Command line and console](command-line-and-console.md) | Every `eax` command in detail, and the console (`eax console`) item by item: for getting EA Explorer back up |
| [Testing](testing.md) | Every kind of test, what each covers, how to run it, who runs it and where the results go; the self-test in detail |
| [The test bench](testbench.md) | `eax testbench`: the self-test's tests from outside, in any browser; install, upgrade and load tests; the test data; reports and CI |
| [Operations](operations.md) | Health, services on and off, backups and restores (console and command line), the maintenance page, upgrades, logs and diagnostics |
| [Release 3: the security review](security-r3.md) | R3.12: what was checked in everything Release 3 adds, what was found and fixed, what is left open and why |
| [Data discovery and ingestion](discovery.md) | The Release 3 epic: OData feeds read, pushes taken and documents read by AI become deliveries to review; only what changed; matches to confirm |
| [Smaller images: the proposal](footprint-proposal.md) | R3.6: per image, how much smaller it could get and what would be lost; for the owner to decide before anything is built |
| [Licences](licences.md) | The open-source components EA Explorer uses and their licences |
| [CI](../ci/README.md) | The checks and tests run on every change |
| [Sample files](../deploy/samples/README.md) | The sample files that come with the deployment |

## How it is built

| Document | What it covers |
| --- | --- |
| [Architecture](architecture.md) | The containers, how they talk to each other, sign-in, the reports and documents services |
| [Database](database.md) | The repository database: schemas, tables, row security, history, report views |
| [MCP server](mcp.md) | Using EA Explorer from AI assistants: connecting, the tools, what each person may do |
| [Architecture projects (design)](design-architecture-projects.md) | The agreed design of architecture projects, the project library and the repository (phases 13 to 13.3) |
| [Decision log](decisions.md) | Every decision with its date and reason (D1 onwards) |
| [To do](todo.md) | Open items and ideas not yet in a phase |
| [For AI coding agents](../AGENTS.md) | The rules for anyone (or any agent) changing the code |

## Requirements and plan

| Document | What it covers |
| --- | --- |
| [Requirements](requirements/EA_Explorer_Requirements.xlsx) | Every requirement with its acceptance criteria, priority and phase |
| [Build plan](requirements/EA_Explorer_Build_Plan.xlsx) | The 57 phases, their order, demos and requirements, and the timeline |
| [High-level requirements](requirements/EA_Explorer_High_Level_Requirements.docx) | The product's purpose, scope and main requirements |
| [Technical architecture](requirements/EA_Explorer_Technical_Architecture.docx) | The technical architecture document |
| [Master template repository](requirements/EA_Explorer_Master_Template_Repository.xlsx) | The project library as reviewed: phases, steps, the master list of deliverables and artifacts, folders and templates |

## The build phases

Each phase has its own notes: what it delivers, a demo, checks, how to upgrade and what is not in it.

| Phase | Notes | State |
| --- | --- | --- |
Every phase in detail, with versions and the planned ones: [build-phases.md](build-phases.md).

| 0 | [Foundations](phase-0.md) | closed |
| 1 | [Metamodel store and the ArchiMate 4 seed](phase-1.md) | closed |
| 2 | [Insurance reference model, locked models, library page and versions](phase-2.md) | closed |
| 3 | [Metamodel editing, versions and history, failing checks, model locks](phase-3.md) | accepted |
| 3.1 | [Roles and permissions](phase-3.1.md) | accepted |
| 4 | [Creating and copying models, library models and packages](phase-4.md) | closed |
| 5 | [Report views and the thirty standard reports](phase-5.md) | closed |
| 6 | [Data entry in forms](phase-6.md) | closed |
| 7 | [Grids, search and saved views](phase-7.md) | closed |
| 8 | [Commits, drafts, approvals and merges](phase-8.md) | closed |
| 8.1 | [Notifications, requests, webhooks, push down, change documents](phase-8.1.md) | closed |
| 8.2 | [Reports and views: views, TOGAF catalogues and matrices](phase-8.2.md) | closed |
| 8.3 | [Model tags, comparison and gap analysis](phase-8.3.md) | closed |
| 8.4 | [Backups and restores](phase-8.4.md) | closed |
| 9 | [The change log](phase-9.md) | closed |
| 10 | [Administration console and application settings](phase-10.md) | closed |
| 10.1 | [Import and export sheets](phase-10.1.md) | closed |
| 12 | [Validation and data quality](phase-12.md) | closed |
| 12.1 | [Start-up in two tiers, open pictures in draw.io](phase-12.1.md) | closed |
| 13 | [Architecture projects, the project library and the repository in Documents](phase-13.md) | closed |
| 13.0.1 | [Setting up and running a project: scope, goals and outcomes, sponsor, editing, sign-off, the ADM landing page, finishing](phase-13.0.1.md) | closed |
| 13.0.3 | [Model roles and project templates as wizards](phase-13.0.3.md) | closed |
| 13.0.4 | [Admin by wizards, architecture on screens, five areas](phase-13.0.4.md) | closed |
| 13.0.5 | [Common analysis](phase-13.0.5.md) | closed |
| 13.0.6 | [The project repository as a table: versions, tags, accept or approve, archive and delete](phase-13.0.6.md) | closed |
| 13.0.2 | [Every slow button as a background task, the task drawer](phase-13.0.2.md) | closed |
| 13.0.7 | [Content framework, tagging, architecture repository links, project organisation, tasks](phase-13.0.7.md) | closed |
| 13.0.8 | [The organisation's reference library](phase-13.0.8.md) | closed |
| 13.0.9 | [The Architecture Repository: calendars, board, performance measurement, reference library parts](phase-13.0.9.md) | closed |
| 13.1 | [Project bases, TOGAF 10 metamodel, standards, governance log, charter; the documents table, repository tags, the Phases tab](phase-13.1.md) | closed |
| 13.2 | [Tracking sheets: light sheets at project and organisation level, Excel in and out](phase-13.2.md) | closed |
| 13.3 | [Turn Projects, Repository and References on or off: a lighter, metamodel-only application](phase-13.3.md) | closed |
| 13.5 | [The console: eax console](phase-13.5.md) | closed |
| 13.8 | [Sample content for the sample projects and the organisation](phase-13.8.md) | closed |
| 13.9 | [The eax command in Python, run by uv](phase-13.9.md) | closed |
| 15.2 | [The library: organisation and project libraries with pages, a separate service](phase-15.2.md) | built (D346 to D351) |
| 16.3 | [Guided wizards: data quality, compliance review, migration plan, collect and load data, first-run setup](phase-16.3.md) | built, waiting for the owner's test |
| 15.3 | [Business architecture artifacts: canvases as views of the model, with gaps](phase-15.3.md) | design session half done |
| story | [Load balancing: servers go up and down with the load](story-load-balancing.md) (production deployment, phase 36) | later |
| story | [Real-time mirrors of PostgreSQL and the other servers](story-real-time-mirrors.md) (production deployment, phase 36) | later |
