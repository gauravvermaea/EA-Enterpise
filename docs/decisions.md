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
