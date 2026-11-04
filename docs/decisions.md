# Decision log

Decisions taken while writing the requirements (3 November 2026). Full context is in
docs/requirements/EA_Explorer_Requirements.xlsx (sheet "Decisions").

| ID | Decision |
| --- | --- |
| D1 | Principle P9: use mature open-source Docker-based products with their own screens; a different look is accepted |
| D2 | Users bring their own language model and connect through MCP; no LLM is shipped |
| D3 | The API and its background jobs share one container |
| D4 | Spreadsheet data is exchanged as CSV only |
| D5 | CSV loads and diagram harvests go through staging and review; web edits publish at once with publish rights |
| D6 | Mayan EDMS is the document repository in every install |
| D7 | Reports are done in Apache Superset only |
| D8 | Our code is licensed AGPL-3.0 |
| D9 | One installation serves one organisation |
| D11 | Branch and merge back is a must |
| D13-D18 | Read-only reference models, deep copy, ten industry models, work copies and merge, dedupe, 30 standard reports and 20 standard views |
| D19 | One release (version 1.0); the build plan sets the order |
| D20 | ArchiMate Model Exchange File Format for exchange with other tools |
| D21 | Config templates for laptop, single server, scale-out and cloud |
| D22 | Each model holds the TOGAF Architecture Repository |
| D23-D25 | Standard views separate from reports; seamless Keycloak sign-in; home page dashboard |
| D26-D27 | Operations insight; deployment scripts for every kind |
| D28 | Every requirement is Must |
| D29-D47 | Phases 0 to 2 decisions: see the Decisions sheet of the requirements workbook |
| D48 | Validation rules warn, never block: a failed rule saves the value with an override flag and its details |
| D49 | A relationship outside the metamodel can be added; it adds the relationship type and mapping, flagged |
| D50 | The model page rebuilt for large models (tabs, type tables, entity page) in phase 2 |
| D51 | Industry pack documents (guidance, workbooks...) live in Mayan, linked from the model library |
| D52 | The SQL window becomes read-only for everyone |
| D53 | Roles and permissions get their own phase (3.1), before data entry, agreed with the user and tested with a test user per role |
| D54 | Version 0.2.1 completes phase 2 (picture kinds, .drawio everywhere, entity timeline, lineage, CSV); additions between phases take a patch number |
| D55 | No concurrent-editing control for repository content: last write wins, history keeps every write; Mayan documents are checked out while edited |
| D56 | No load, volume or penetration testing: performance and security targets stay design targets |
| D57 | The entity page draws one entity in seven ways (neighbourhood, both ways, one way, family tree, by layer, path, as it was) |
| D58 | Eight roles: Super Admin, IT Admin, User Admin, Keycloak Admin, Model Admin, Architect, Model Sub Admin, Report Viewer; test users for each on laptops |
| D59 | Users are assigned to roles (what) and separately to models (where); the Model Admin assigns models; permissions enforced in the API and database |
| D60 | Users of a derived model get read-only access to the models it comes from, for lineage |
| D61 | No commits until a commits phase designed with the user; every save visible at once; git-like compare and merge screens |
| D62 | Document management in Mayan is a whole phase, designed with the user first; a document repository per model |
| D63 | Lineage shows ancestors, what changed and where it was edited, and merges; a merged model becomes read-only and work continues in a fresh child |
| D64 | A metamodel change is never blocked by existing content: defaults (empty allowed), optionally applied to existing entities; a failing-checks screen |
| D65 | The metamodel has a version and a history view; every entity records the metamodel version it was created and last changed in |
| D66 | Merging a child back carries its metamodel changes into the parent with its content |
| D67 | Model Admins lock models three ways (metamodel; metamodel and content; maintenance) until they unlock them; enforced by the database |
| D68 | Dedupe works within one model only |
| D69 | Model Admins get a change log report of who changed what |
| D70 | Custom views can be shared as view templates; what a template cannot express becomes a development feature |
| D71 | The metamodel is exposed for report builders: catalogue API, described Superset datasets, report designer |
| D72 | Each metamodel change publishes a new metamodel version at once, with a note; there are no drafts |
| D73 | Active Directory and LDAP sign-in are not planned for now (SEC-003 moved out of phase 4); Keycloak's own users only |
| D74 | Complete backup and restore: all databases with their history, Mayan files, Keycloak users and roles, Superset; the backup location (server or folder) chosen from the web; scheduled; restore from the web |
| D75 | Removing an attribute removes its values; removing a relationship type removes its relationships; both stay in history |
| D76 | Technical documentation and hand-over files for other AI agents (docs/architecture.md, CLAUDE.md, AGENTS.md) are kept current every phase |
| D77 | Import, export and survey sheets are generated from the metamodel: choose entity types; one sheet per type plus one for relationships. Open: an Excel workbook or a CSV set (relationships need to point at real entities) |
| D78 | Collection sets: send out sheets, upload what comes back to a staging area, review and edit in the application, then load |
| D79 | Data entry page: choose an entity type and its columns appear; a + on each row adds relationships, to existing entities only (a new entity is saved first) |
| D80 | A break-glass local account with Super Admin rights works when Keycloak or sign-in is down; sealed password, every use audited and alerted |
| D81 | Model hierarchy: a read-only Empty model, then root metamodels (kind "Root metamodel", with framework and version: ArchiMate 4, later ArchiMate 5, or an organisation's own), then reference and project models. Shipped roots are read-only; an organisation's roots are edited by Model Admins until locked; a root starts empty or from a copy of another root (phase 4). Built early in 0.3.1: the top model (named Root, D107), ArchiMate 4 under it, and a sample root built from scratch ("Lean EA metamodel", editable by its Model Admin) with a project model under it |
| D82 | A model moves to a new framework version either by a copy with a type mapping or by an in-place upgrade (history keeps the state before); both are offered |
| D83 | Actions, alerts and workflows get their own phase (8.1, after commits): notifications kept open until resolved with a description of what was done; requests between people (new attribute, review, model copy, ...); kinds agreed in a design session |
| D84 | A parent's metamodel change is pushed only to the models under it: forced (with or without defaults) or offered for accept or reject by the child's Model Admin; each level decides and may force it further down; a rejection leaves the child diverged, noted in lineage, and later changes to that item ask again |
| D85 | Notifications go to a role on the model plus anyone subscribed; each is resolved once, by whoever handles it |
| D86 | Notifications are in the application only (no email); every accepted change produces a detailed change document notified to everyone on the model |
| D87 | A retired entity type offers no new entities and its entities are read-only until it is restored (unretired); enforced by the database (phase 3) |
| D88 | Import, export and survey sheets come both as an Excel workbook (for people) and as a set of CSV files (for feeds) |
| D89 | Only Model Admins (and the Super Admin) change a model's metamodel; Architects ask through a request |
| D90 | Model Admins also edit content and, once commits exist, commit it |
| D91 | A new integration phase (34.1): import from other systems' APIs, our own API and file dumps through a proper drag-and-drop ETL tool with standard connectors; the tool is chosen with the owner before the phase |
| D92 | Global roles are given in Keycloak, never in EA Explorer; EA Explorer maps Keycloak roles to its global roles (core.role_mappings, edited by User Admins); roles on models are given in EA Explorer (D96) |
| D93 | When Active Directory comes, its groups are managed in Keycloak and mapped to Keycloak roles; EA Explorer never reads the directory |
| D94 | Reports and views can span every model a person may read, across metamodels, each element marked with its model |
| D95 | Laptops get test models for roles and lineage: Fynbos Mutual (group, from the insurance reference model), Fynbos Life and Fynbos Commercial (derived lines of business), Karoo Re (from the ArchiMate 4 template) |
| D96 | Two kinds of role: global roles given in Keycloak (Super Admin, IT Admin, User Admin, Keycloak Admin, Model Creator, User) and model roles given per model in EA Explorer (Model Admin, Model Sub Admin, Architect, Report Viewer); one person may have different roles on different models and several on one |
| D97 | Model Creators and Super Admins create models (a Model Admin may derive from theirs); the creator becomes the new model's Model Admin; roles are not copied to derived models, whose people read the model they come from |
| D98 | The library (templates and reference models) is open to everyone signed in; only Super Admins read every working model; User Admins read no model content |
| D99 | Productionising stories for the final deployment scripts (phase 36), to discuss then: scale-out, users on another identity platform, integrated AD sign-in, sign-in and paths set in the config file, and a key vault for every password |
| D100 | A break-glass session does not expire: it lasts until the person signs out or the break-glass password is changed (which ends every session) |
| D101 | The model library has a browser on the left (root metamodels, then the reference models on each root, with a search and a filter) and the chosen model on the right (0.3.1). Library models grow in phase 4: create a model as a library model with its pack (guidance, workbooks, reports, diagrams), promote any model to the library, and download or upload a library model as one package file so experts can build and share them |
| D102 | One set of marks on every list, tree and model page: kind (◆ root metamodel, ▣ reference model, ● project model), 📚 in the library, 👁 read-only (for everyone, or for you), 🔒 locked by a Model Admin; with a legend and a tooltip saying why |
| D103 | Architecture projects (phase 15), loosely coupled to models: several projects can work on one model and update it, or a project can work on a copy and merge it back; what happens to a project's content on close, merge or abandon is settled in the design session. Each project says which ADM phase it is in, with a history of moves and gate reviews; the ADM is tailored per project from a framework definition in the library |
| D104 | Registers are organisation-wide (principles, standards, glossary, reference library, architecture capability; principles are versioned and kept up to date, and the projects following one are told when it changes) or per project (decision log, governance log, requirements, risks and issues, change requests, the project's metamodel record), with roll-ups across projects |
| D105 | Every deliverable and artefact a project needs is produced from library templates, reviewed, approved and stored read-only in the project's document store by ADM phase. The architecture repository is built over five phases: 15 projects and the ADM, 15.1 organisation-wide repository, 16 project registers, 16.1 project setup, 16.2 artefacts; design session first |
| D106 | A library model's pack is not limited to its set places (guidance, workbooks, reports, diagrams...): its builders can add any number of other files of any kind, each with a name, a description and a folder of their choosing; they travel in its package (phase 4) |
| D107 | Everything goes through nginx on https. On a laptop EA Explorer makes a local certificate authority (its key is thrown away and it may vouch only for this installation's names) and signs the site certificate with it; `eax trust` adds it to the computer's trusted certificates once, and clean-run keeps it (work/data/tls). The direct ports 8000 and 8001 are gone; on a laptop the API (Swagger) and the MCP server also answer on plain http, bound to the computer itself; on a server http only redirects. The top model of the hierarchy is called **Root** (was Empty) |
| D108 | Model and library model packages (phase 4) are uploaded as coming from a separate installation, through a wizard that places them in the hierarchy: under their root metamodel, matched by name and version (a library model may only be built on a root metamodel shipped as seed, and must match it completely; a mismatch lists the differences), or attached under the Root model with all its values, as a root of its own |
| D109 | The start page shows a card for everything agreed and still to come, grouped, with the build phase that delivers it ("agreed; phase to be set" for backlog items); services.js is kept in step with the build plan |
| D110 | Looking at an entity as it was at a moment of its history highlights what that change itself did: values it changed (marked "changed here" and shown in the Then column as old → new, the old value struck through in red), relationships it added (green) and removed (red) |
| D111 | Model versions, comparison and gap analysis get a phase of their own after the reports (24.1), with a design session first to keep the noise out: named versions and roll-back, compare a model with its own versions or with another model (matched by origin, then display ID, then type and name; manual matches kept), comparison profiles and a summary first, renames shown as one change, gap analysis (kept, changed, new, eliminated) with notes and resolutions, and a gap report (Superset, Word, Excel). Named versions, roll-back and comparison move there from phase 9 |
| D112 | Views, diagrams, reports and dashboards download as PowerPoint (.pptx): one slide each with title, legend, source model, version and date; several gathered into one deck in a chosen order (a slide basket); on the organisation's own slide template when uploaded. Diagrams as SVG pictures, tables as editable PowerPoint tables, Superset charts from its report screenshots. Built in phase 31, when views and reports both exist |
| D113 | Every entity has a Rules tab: every rule applied to it (required attributes, pick lists, value rules, duplicate names, relationships it must have), each passed, failed or not applicable with the value checked and why, failed first, and each of its relationships against the metamodel. New rule type Has relationship (migration 0007): at least one relationship of a type (or any) to or from an entity of a type (or any), either direction; it warns like every rule and shows in Failing checks. The laptop seed puts four relationship rules and six rule-breaking entities in Karoo Re |
| D114 | The product, its code, screens, documents and workbooks name no other EA platform or vendor product; requirements found by reviewing commercial EA repositories carry the source "Market review". (Integration targets such as ServiceNow, Entra ID, Power BI or Visio stay, because connecting to them is the requirement.) |
