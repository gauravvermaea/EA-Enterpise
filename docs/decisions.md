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
| D81 | Model hierarchy: a read-only Empty model, then root metamodels (kind "Root metamodel", with framework and version: ArchiMate 4, later ArchiMate 5, or an organisation's own), then reference and project models. Shipped roots are read-only; an organisation's roots are edited by Model Admins until locked; a root starts empty or from a copy of another root (phase 4) |
| D82 | A model moves to a new framework version either by a copy with a type mapping or by an in-place upgrade (history keeps the state before); both are offered |
