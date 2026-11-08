# Documentation

Every document of EA Explorer, in one place. Start with the [README](../README.md): what EA Explorer is, the quick start,
the `eax` commands (backups and restores included) and the phase table.

## Running it

| Document | What it covers |
| --- | --- |
| [README](../README.md) | Quick start on a laptop, the `eax` commands, the work folder, certificates, the phase table |
| [Operations](operations.md) | Health, services on and off, backups and restores (console and command line), the maintenance page, upgrades, logs and diagnostics |
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
| 8.2 | [Reports and views: viewpoints, TOGAF catalogues and matrices](phase-8.2.md) | closed |
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
| 13.0.9 | [The Architecture Repository structure](phase-13.0.9.md) | planned: its own design session first |
| 13.1 | [Project bases, TOGAF 10 metamodel, standards, governance log, charter; the documents table, repository tags, the Phases tab](phase-13.1.md) | closed |
| 13.2 | [Tracking sheets: light sheets at project and organisation level, Excel in and out](phase-13.2.md) | requested for later |
| 13.3 | [Turn Projects, Repository and References on or off: a lighter, metamodel-only application](phase-13.3.md) | requested for later |
| 13.4 | [Reference library with pages: an open-source wiki beside links and documents](phase-13.4.md) | requested for later |
| 13.5 | [A console app: an interactive session with EA Explorer](phase-13.5.md) | requested for later |
| 13.6 | [Load balancing: servers go up and down with the load](phase-13.6.md) | requested for later |
| 13.7 | [Real-time mirrors of PostgreSQL and the other servers](phase-13.7.md) | requested for later |
| 13.8 | [More sample projects and models that show how to use EA Explorer](phase-13.8.md) | requested for later |
