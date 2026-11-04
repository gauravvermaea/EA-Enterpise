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
